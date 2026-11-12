#!/usr/bin/env python3
"""
Security Test Suite (black-box, paper instance, test accounts only)
===================================================================
S1  Unauthenticated access          every OMS / admin endpoint without a token must answer 401/403
S2  Invalid / tampered tokens       garbage, empty, altered-last-char and swapped tokens must be rejected
S3  Horizontal privilege (IDOR)     user A must not squareoff / reduce / protect / cancel user B's position or order
S4  Vertical privilege              a trader token / cookie must not reach admin APIs (and cannot create or fund members)
S5  Copy-trading data exposure      a follower must not see the master's follower list
S6  Login hardening                 user enumeration, rate limiting / lockout, long-lived session cookie
S7  Injection                       SQLi / XSS / traversal / null bytes in login and order fields: never 5xx, never auth bypass
S8  Malformed & oversized requests  bad JSON, wrong content-type, 2 MB body, wrong methods: clean 4xx, never 5xx
S9  Transport & headers             HTTP->HTTPS, HSTS, CSP, X-Frame-Options, cookie flags, CORS, TLS version
S10 Error hygiene                   errors must not leak stack traces, file paths or SQL

Severity: HIGH = exploitable / broken access control or 5xx on hostile input   MED = weakness   INFO = observation
Nothing here changes data except what an attacker could (the IDOR checks target throw-away follower positions).

Usage:   python test_suite/security_runner.py
"""
import argparse
import json
import socket
import ssl
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config.settings import BASE_URL, DEFAULT_PREFIX, DEFAULT_DOMAIN, MASTER_EMAIL, MEMBER_PASSWORD
from test_suite.breakpoint_race_runner import Findings, mkt_id, ord_id
from test_suite.client import BlackTraderClient

SYM = "BINANCE:BTCUSDT.P"
T = 15


def http(method, path, token=None, json_body=None, data=None, headers=None, inst="paper"):
    h = dict(headers or {})
    if token is not None:
        h["Authorization"] = f"Bearer {token}"
    h.setdefault("X-Broker-ID", inst)
    try:
        return requests.request(method, BASE_URL + path, json=json_body, data=data, headers=h, timeout=T, allow_redirects=False)
    except Exception as e:
        class R:  # noqa
            status_code, text, headers = 599, f"EXC {type(e).__name__}: {e}", {}
        return R()


def leaks(text: str):
    low = (text or "").lower()
    return [m for m in ("traceback", "stack trace", "exception in", ".go:", "/usr/", "/home/", "c:\\", "select ", "syntax error", "sqlstate",
                        "psycopg", "mysql", "sqlite", "panic:") if m in low]


def s1_unauth(ctx):
    print("\n[S1] Unauthenticated access")
    F = Findings("S1 Unauthenticated access")
    eps = [("GET", "/v1/oms/paper/positions"), ("GET", "/v1/oms/paper/orders"), ("GET", "/v1/oms/paper/history"),
           ("POST", "/v1/oms/paper/orders"), ("GET", "/v1/oms/paper/copy/follows"), ("GET", "/v1/oms/paper/copy/masters"),
           ("POST", "/v1/oms/paper/copy/follow"), ("GET", "/admin/api/members"), ("POST", "/admin/api/members"),
           ("POST", "/api/auth/chart-token")]
    for m, p in eps:
        r = http(m, p, token=None, json_body={} if m == "POST" else None)
        if r.status_code in (200, 201):
            F.add("HIGH", f"{m} {p} answered {r.status_code} WITHOUT credentials")
        elif r.status_code >= 500:
            F.add("HIGH", f"{m} {p} returned {r.status_code} without credentials")
    F.metrics["endpoints_checked"] = len(eps)
    return F.result()


def s2_tokens(ctx):
    print("\n[S2] Invalid / tampered tokens")
    F = Findings("S2 Invalid and tampered tokens")
    good = ctx.token_a
    tampered = good[:-1] + ("A" if good[-1] != "A" else "B")
    swapped_mid = good[:len(good) // 2] + good[len(good) // 2:][::-1]
    for label, tok in [("empty", ""), ("garbage", "not-a-token"), ("altered last char", tampered), ("scrambled", swapped_mid),
                       ("null byte", good + "\x00"), ("huge", "A" * 20000), ("sql-ish", "' OR '1'='1")]:
        try:
            r = http("GET", "/v1/oms/paper/positions", token=tok)
        except Exception as e:
            continue
        if r.status_code == 200:
            F.add("HIGH", f"token variant '{label}' was ACCEPTED (HTTP 200)")
        elif r.status_code >= 500:
            F.add("HIGH", f"token variant '{label}' caused HTTP {r.status_code}")
    r = http("GET", "/v1/oms/paper/positions", headers={"Authorization": "Basic YWRtaW46YWRtaW4="})
    if r.status_code == 200:
        F.add("HIGH", "HTTP Basic admin:admin accepted")
    for hdr in ({"X-User-Id": "admin"}, {"X-Forwarded-For": "127.0.0.1"}, {"X-Original-URL": "/admin"}):
        r = http("GET", "/admin/api/members", headers=hdr)
        if r.status_code == 200:
            F.add("HIGH", f"admin API reachable by spoofing header {list(hdr)[0]}")
    return F.result()


def s3_idor(ctx):
    print("\n[S3] Horizontal privilege (IDOR): follower A against follower B's resources")
    F = Findings("S3 IDOR (cross-account access)")
    c, A, B = ctx.c, ctx.a, ctx.b
    c.bulk_cancel(B, "paper"); c.bulk_squareoff(B, "paper")
    pos_b = mkt_id(c.place_order(B, qty=0.01, instance="paper"))
    pend = c.place_order(B, side="BUY", order_type="LIMIT", qty=0.01, price=1000.0, instance="paper")
    ord_b = ord_id(pend)
    if not pos_b:
        F.add("INFO", "could not open victim position; skipped"); return F.result("SKIP")
    ta = ctx.token_a
    attacks = [("squareoff B's position", "POST", f"/v1/oms/paper/positions/{pos_b}/squareoff", {}),
               ("reduce B's position", "POST", f"/v1/oms/paper/positions/{pos_b}/reduce", {"qty": 0.005}),
               ("set protection on B's position", "PUT", f"/v1/oms/paper/positions/{pos_b}/protection", {"tp": 999999, "sl": 1})]
    if ord_b:
        attacks.append(("cancel B's pending order", "DELETE", f"/v1/oms/paper/orders/{ord_b}", None))
    for label, m, p, body in attacks:
        r = http(m, p, token=ta, json_body=body)
        if r.status_code == 200:
            F.add("HIGH", f"IDOR: follower A was able to {label} (HTTP 200)")
        elif r.status_code >= 500:
            F.add("HIGH", f"{label}: HTTP {r.status_code} instead of 403/404")
    time.sleep(1.0)
    still = [p for p in c.get_positions(B, "paper").get("positions", []) if p.get("market_order_id") == pos_b]
    if not still:
        F.add("HIGH", "victim's position disappeared after cross-account attempts")
    bids = {o.get("order_id") for o in c.get_orders(A, "paper").get("orders", [])}
    if pos_b in bids or (ord_b and ord_b in bids):
        F.add("HIGH", "follower A's order list contains follower B's orders")
    c.bulk_cancel(B, "paper"); c.bulk_squareoff(B, "paper")
    F.metrics["attacks"] = len(attacks)
    return F.result()


def s4_vertical(ctx):
    print("\n[S4] Vertical privilege: trader credentials against admin APIs")
    F = Findings("S4 Vertical privilege (trader -> admin)")
    sess = requests.Session()
    sess.post(BASE_URL + "/api/auth/login", json={"email": ctx.a, "password": MEMBER_PASSWORD}, timeout=T)
    cookie_session_calls = [("GET", "/admin/api/members", None), ("POST", "/admin/api/members/mem_doesnotexist000/balance",
                            {"instance": "paper", "balance": 1, "remark": "sec-test", "force": True}),
                            ("POST", "/admin/api/members/mem_doesnotexist000/status", {"status": "disabled"}),
                            ("POST", "/admin/api/members/mem_doesnotexist000/book", {"book": "a"}),
                            ("POST", "/admin/api/members", {})]
    for m, p, body in cookie_session_calls:
        for how in ("trader cookie", "chart token"):
            try:
                if how == "trader cookie":
                    r = sess.request(m, BASE_URL + p, json=body, timeout=T, allow_redirects=False)
                else:
                    r = http(m, p, token=ctx.token_a, json_body=body)
            except Exception:
                continue
            code = r.status_code
            if code in (200, 201):
                F.add("HIGH", f"PRIVILEGE ESCALATION: {m} {p} succeeded with a {how}")
            elif code == 404 and "balance" in p or code == 404 and "status" in p or code == 404 and "book" in p:
                F.add("MED", f"{m} {p} with a {how} reached the handler (404 not 401/403) - authorization should come before lookup")
            elif code >= 500:
                F.add("HIGH", f"{m} {p} with a {how} returned {code}")
    return F.result()


def s5_copy_exposure(ctx):
    print("\n[S5] Copy-trading data exposure")
    F = Findings("S5 Copy-trading data exposure")
    r = http("GET", "/v1/oms/paper/copy/follows", token=ctx.token_a)
    if r.status_code == 200:
        try:
            rows = r.json().get("followers", [])
        except Exception:
            rows = []
        others = [x for x in rows if x.get("follower_name") not in (ctx.a.split("@")[0],)]
        F.metrics["rows_visible_to_follower"] = len(rows)
        if others:
            F.add("HIGH", f"a plain follower can list {len(others)} OTHER followers of the master (names, ids, multipliers)")
    return F.result()


def s6_login(ctx):
    print("\n[S6] Login hardening")
    F = Findings("S6 Login hardening")
    t0 = time.time(); r1 = requests.post(BASE_URL + "/api/auth/login", json={"email": "nobody-" + str(int(t0)) + "@mailinator.com", "password": "wrong-pass-1"}, timeout=T)
    d1 = time.time() - t0
    t0 = time.time(); r2 = requests.post(BASE_URL + "/api/auth/login", json={"email": ctx.spare, "password": "wrong-pass-1"}, timeout=T)
    d2 = time.time() - t0
    F.metrics.update(unknown_user=[r1.status_code, r1.text[:80]], known_user_wrong_pw=[r2.status_code, r2.text[:80]],
                     timing_ms=[round(d1 * 1000), round(d2 * 1000)])
    if (r1.status_code, r1.text.strip()) != (r2.status_code, r2.text.strip()):
        F.add("MED", f"user enumeration: unknown email -> {r1.status_code} {r1.text[:60]!r} vs known email -> {r2.status_code} {r2.text[:60]!r}")
    codes = []
    for i in range(40):                                  # one NON-EXISTENT email: cannot lock a real account
        rr = requests.post(BASE_URL + "/api/auth/login", json={"email": "ratelimit-probe@mailinator.com", "password": f"bad{i}"}, timeout=T)
        codes.append(rr.status_code)
        if rr.status_code == 429:
            break
    F.metrics["rapid_bad_logins"] = {"attempts": len(codes), "codes": sorted(set(codes))}
    if 429 not in codes and not any(c_ in (403, 423) for c_ in codes):
        F.add("MED", f"no rate limiting / lockout after {len(codes)} rapid failed logins (codes {sorted(set(codes))}) - brute force is unthrottled")
    r = requests.post(BASE_URL + "/api/auth/login", json={"email": ctx.a, "password": MEMBER_PASSWORD}, timeout=T)
    sc = r.raw.headers.getlist("Set-Cookie")
    exp = [p for h in sc for p in h.split(";") if p.strip().lower().startswith("expires")]
    if exp:
        try:
            when = datetime.strptime(exp[0].split("=", 1)[1].strip(), "%a, %d %b %Y %H:%M:%S GMT")
            days = (when - datetime.utcnow()).days
            F.metrics["session_cookie_days"] = days
            if days > 30:
                F.add("INFO", f"session cookie lives {days} days (long-lived; consider shorter for a trading platform)")
        except Exception:
            pass
    return F.result()


def s7_injection(ctx):
    print("\n[S7] Injection")
    F = Findings("S7 Injection")
    payloads = ["' OR '1'='1' --", "admin'--", "\" OR \"\"=\"", "'; DROP TABLE members;--", "<script>alert(1)</script>",
                "../../../../etc/passwd", "${jndi:ldap://x/a}", "{{7*7}}", "%00", "A" * 5000]
    for pl in payloads:
        r = requests.post(BASE_URL + "/api/auth/login", json={"email": pl, "password": pl}, timeout=T)
        if r.status_code == 200:
            F.add("HIGH", f"login ACCEPTED injection payload {pl[:30]!r}")
        elif r.status_code >= 500:
            F.add("HIGH", f"login returned {r.status_code} for payload {pl[:30]!r}")
        lk = leaks(r.text)
        if lk:
            F.add("MED", f"login error for {pl[:25]!r} leaks internals {lk}")
    for pl in payloads:
        r = http("POST", "/v1/oms/paper/orders", token=ctx.token_a, json_body={"symbol": pl, "side": "BUY", "type": "MARKET", "qty": 0.01})
        if r.status_code == 200:
            F.add("HIGH", f"order accepted with injection symbol {pl[:30]!r}")
        elif r.status_code >= 500:
            F.add("HIGH", f"order symbol {pl[:30]!r} -> HTTP {r.status_code}")
    for pid in ["../../admin/api/members", "..%2F..%2Fadmin", "ord_x'; --", "%00"]:
        r = http("POST", f"/v1/oms/paper/positions/{pid}/squareoff", token=ctx.token_a, json_body={})
        if r.status_code == 200 or r.status_code >= 500:
            F.add("HIGH", f"path id {pid!r} -> HTTP {r.status_code}")
    ctx.c.bulk_squareoff(ctx.a, "paper")
    return F.result()


def s8_malformed(ctx):
    print("\n[S8] Malformed & oversized requests")
    F = Findings("S8 Malformed and oversized requests")
    cases = [("invalid JSON", dict(data="{bad json", headers={"Content-Type": "application/json"})),
             ("empty body", dict(data="", headers={"Content-Type": "application/json"})),
             ("JSON array not object", dict(data="[1,2,3]", headers={"Content-Type": "application/json"})),
             ("wrong content-type", dict(data="symbol=X&side=BUY", headers={"Content-Type": "application/x-www-form-urlencoded"})),
             ("deeply nested JSON", dict(data="[" * 5000 + "]" * 5000, headers={"Content-Type": "application/json"})),
             ("2 MB body", dict(data=json.dumps({"symbol": SYM, "side": "BUY", "type": "MARKET", "qty": 1, "pad": "A" * 2_000_000}),
                                headers={"Content-Type": "application/json"}))]
    for label, kw in cases:
        r = http("POST", "/v1/oms/paper/orders", token=ctx.token_a, **kw)
        if r.status_code >= 500:
            F.add("HIGH", f"{label}: HTTP {r.status_code} (should be 4xx)")
        elif r.status_code == 200:
            F.add("HIGH", f"{label}: request ACCEPTED")
    for m in ("PUT", "PATCH", "DELETE"):
        r = http(m, "/v1/oms/paper/orders", token=ctx.token_a, json_body={})
        if r.status_code >= 500:
            F.add("MED", f"{m} /orders -> HTTP {r.status_code} (expected 404/405)")
    ctx.c.bulk_squareoff(ctx.a, "paper")
    return F.result()


def s9_transport(ctx):
    print("\n[S9] Transport & headers")
    F = Findings("S9 Transport and headers")
    u = urlparse(BASE_URL)
    r = requests.get(BASE_URL.replace("https://", "http://"), allow_redirects=False, timeout=T)
    F.metrics["http_status"] = r.status_code
    if r.status_code == 200:
        F.add("MED", "plain http:// returns 200 and is not redirected to https:// (HSTS only protects after the first visit)")
    h = requests.get(BASE_URL + "/dashboard", timeout=T).headers
    F.metrics["headers"] = {k: h.get(k) for k in ("strict-transport-security", "x-content-type-options", "x-frame-options",
                                                  "content-security-policy", "referrer-policy", "permissions-policy", "server")}
    if "strict-transport-security" not in {k.lower() for k in h}:
        F.add("MED", "no Strict-Transport-Security header")
    if not h.get("content-security-policy"):
        F.add("MED", "no Content-Security-Policy header (XSS defence in depth)")
    if not h.get("x-frame-options") and "frame-ancestors" not in (h.get("content-security-policy") or ""):
        F.add("MED", "clickjacking: no X-Frame-Options / frame-ancestors")
    if not h.get("referrer-policy"):
        F.add("INFO", "no Referrer-Policy header")
    if h.get("x-content-type-options", "").count("nosniff") > 1:
        F.add("INFO", "X-Content-Type-Options sent twice ('nosniff, nosniff') - harmless but two layers add it")
    for hdr in ("x-powered-by", "x-aspnet-version"):
        if h.get(hdr):
            F.add("INFO", f"{hdr} discloses {h.get(hdr)}")
    # CORS
    for origin in ("https://evil.example", "null"):
        rr = requests.options(BASE_URL + "/v1/oms/paper/positions", headers={"Origin": origin, "Access-Control-Request-Method": "GET",
                                                                              "Access-Control-Request-Headers": "authorization"}, timeout=T)
        acao, acac = rr.headers.get("access-control-allow-origin"), rr.headers.get("access-control-allow-credentials")
        if acao == "*" or acao == origin:
            F.add("HIGH" if acac == "true" else "MED", f"CORS allows origin {origin!r} (ACAO={acao}, credentials={acac})")
    # TLS
    try:
        ctx_ = ssl.create_default_context()
        with socket.create_connection((u.hostname, 443), timeout=T) as s_:
            with ctx_.wrap_socket(s_, server_hostname=u.hostname) as ss:
                F.metrics["tls"] = ss.version()
                if ss.version() in ("TLSv1", "TLSv1.1", "SSLv3"):
                    F.add("HIGH", f"weak TLS version negotiated: {ss.version()}")
        for name, ver in (("TLS 1.0", ssl.TLSVersion.TLSv1), ("TLS 1.1", ssl.TLSVersion.TLSv1_1)):
            try:
                c2 = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT); c2.check_hostname = False; c2.verify_mode = ssl.CERT_NONE
                c2.minimum_version = ver; c2.maximum_version = ver
                with socket.create_connection((u.hostname, 443), timeout=T) as s_:
                    with c2.wrap_socket(s_, server_hostname=u.hostname):
                        F.add("MED", f"server still accepts {name}")
            except Exception:
                pass
    except Exception as e:
        F.add("INFO", f"TLS probe skipped: {type(e).__name__}")
    # cookie flags
    r = requests.post(BASE_URL + "/api/auth/login", json={"email": ctx.a, "password": MEMBER_PASSWORD}, timeout=T)
    for raw in r.raw.headers.getlist("Set-Cookie"):
        low = raw.lower()
        for flag in ("httponly", "secure", "samesite"):
            if flag not in low:
                F.add("MED", f"cookie {raw.split('=')[0]} lacks {flag}")
    return F.result()


def s10_errors(ctx):
    print("\n[S10] Error hygiene")
    F = Findings("S10 Error hygiene")
    probes = [("GET", "/v1/oms/paper/nope"), ("POST", "/v1/oms/paper/orders"), ("GET", "/admin/api/nope"), ("GET", "/api/auth/nope"),
              ("POST", "/v1/oms/paper/orders")]
    for m, p in probes:
        r = http(m, p, token=ctx.token_a, json_body={"type": "WEIRD", "symbol": SYM, "side": "BUY", "qty": 1} if p.endswith("orders") else None)
        lk = leaks(r.text)
        if lk:
            F.add("MED", f"{m} {p} -> {r.status_code} leaks {lk}: {r.text[:100]!r}")
    return F.result()


class Ctx:
    pass


SCENARIOS = {"S1": s1_unauth, "S2": s2_tokens, "S3": s3_idor, "S4": s4_vertical, "S5": s5_copy_exposure,
             "S6": s6_login, "S7": s7_injection, "S8": s8_malformed, "S9": s9_transport, "S10": s10_errors}


def main() -> int:
    ap = argparse.ArgumentParser(description="Black-box security checks")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    ctx = Ctx()
    ctx.c = BlackTraderClient(base_url=BASE_URL, max_workers=4)
    ctx.a, ctx.b, ctx.spare = (f"{DEFAULT_PREFIX}{i}@{DEFAULT_DOMAIN}" for i in (2, 3, 4))
    ctx.token_a = ctx.c.get_trader_token(ctx.a)
    print("=" * 80 + "\n SECURITY SUITE | paper instance | attacker=follower2 victim=follower3\n" + "=" * 80)
    wanted = [s.strip().upper() for s in a.only.split(",") if s.strip()] or list(SCENARIOS)
    results = []
    for k in wanted:
        fn = SCENARIOS.get(k)
        if fn:
            try:
                results.append(fn(ctx))
            except Exception as e:
                print(f"  => {k}: ERROR {type(e).__name__}: {e}")
                results.append({"name": k, "status": "ERROR", "metrics": {}, "findings": [{"severity": "HIGH", "message": f"runner exception: {e}"}]})
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = BASE_DIR / "reports" / "evidence"; out.mkdir(parents=True, exist_ok=True)
    jp, mp = out / f"security_evidence_{ts}.json", out / f"security_evidence_{ts}.md"
    jp.write_text(json.dumps({"suite": "Security", "timestamp": datetime.now(timezone.utc).isoformat(), "results": results}, indent=2, default=str), encoding="utf-8")
    icon = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌", "SKIP": "⏭️", "ERROR": "💥"}
    md = ["# Security Test Report", "", f"**Generated:** {datetime.now(timezone.utc).isoformat()}  ", f"**Target:** `{BASE_URL}` (paper, test accounts)", "",
          "| Check | Result | HIGH | MED |", "| :--- | :---: | ---: | ---: |"]
    for r in results:
        hi = sum(f["severity"] == "HIGH" for f in r["findings"]); me = sum(f["severity"] == "MED" for f in r["findings"])
        md.append(f"| {r['name']} | {icon.get(r['status'], '?')} {r['status']} | {hi} | {me} |")
    md += ["", "## Findings", ""]
    for r in results:
        if r["findings"]:
            md.append(f"### {r['name']}"); md += [f"- **{f['severity']}** - {f['message']}" for f in r["findings"]]; md.append("")
    mp.write_text("\n".join(md) + "\n", encoding="utf-8")
    tally = {}
    for r in results:
        tally[r["status"]] = tally.get(r["status"], 0) + 1
    print("\n" + "=" * 80 + f"\n SUMMARY: {tally}\n Report : {mp}\n" + "=" * 80)
    return 1 if any(r["status"] in ("FAIL", "ERROR") for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
