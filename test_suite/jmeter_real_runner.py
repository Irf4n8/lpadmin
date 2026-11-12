#!/usr/bin/env python3
"""
Real Apache JMeter load test (replaces the old Python simulation)
=================================================================
1. creates fresh auth tokens for the master + followers (kept in a temp dir, deleted afterwards)
2. runs tests/jmeter/blacktrader_oms_load_test.jmx with the real `jmeter` in non-GUI mode
3. parses the JTL results: per-request count, errors, avg/p50/p90/p95/p99/max, throughput
4. gates each request type on error rate and p95 latency (SLA)
5. audits platform state afterwards: every copied position must have been closed (no orphans, no stuck margin)
6. writes evidence (JSON + Markdown) and JMeter's own HTML dashboard under reports/jmeter/<timestamp>/

Profiles (paper instance only unless --i-understand-real-money):
    smoke     a few threads, ~1 min       - sanity check the plan and the platform
    standard  realistic launch-day load   - the one to gate on
    stress    heavy                       - to find where it degrades

Install JMeter once:   python scripts/install_jmeter.py
Run:                   python test_suite/jmeter_real_runner.py --profile standard --end 100
"""
import argparse
import csv
import glob
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config.settings import BASE_URL, DEFAULT_PREFIX, DEFAULT_DOMAIN, MASTER_EMAIL, MASTER_ID, MEMBER_PASSWORD, FOLLOWER_COUNT
from test_suite.client import BlackTraderClient

PLAN = BASE_DIR / "tests" / "jmeter" / "blacktrader_oms_load_test.jmx"
TOOLS = Path(os.environ.get("BT_TOOLS_DIR", Path.home() / "tools"))

PROFILES = {
    "smoke":    dict(RAMP=3,  AUTH_THREADS=5,  AUTH_LOOPS=2, ORDER_THREADS=5,  ORDER_LOOPS=2, READ_THREADS=10,  READ_DURATION=15, HIST_THREADS=2,  HIST_LOOPS=2, tokens=20),
    "standard": dict(RAMP=10, AUTH_THREADS=20, AUTH_LOOPS=3, ORDER_THREADS=20, ORDER_LOOPS=5, READ_THREADS=50,  READ_DURATION=30, HIST_THREADS=5,  HIST_LOOPS=3, tokens=50),
    "stress":   dict(RAMP=20, AUTH_THREADS=40, AUTH_LOOPS=3, ORDER_THREADS=50, ORDER_LOOPS=4, READ_THREADS=100, READ_DURATION=60, HIST_THREADS=10, HIST_LOOPS=3, tokens=100),
}

# p95 latency budget in ms per request type (tune with --sla "ORDER place market=3000").
# Chosen from measured behaviour: 100 concurrent master orders -> p95 ~4.7s, so 5s is the ceiling we gate on.
SLA_P95_MS = {"AUTH login": 2500, "AUTH chart-token": 2500, "ORDER place market": 5000, "ORDER close position": 5000,
              "READ positions": 2500, "READ orders (history)": 6000}
MAX_ERROR_PCT = 1.0
KNOWN_BUG_LABELS = {"NEG unknown order type": "unknown order type returns 500 instead of 400",
                    "NEG absurd tp/sl": "absurd TP/SL (tp=-1, sl=1e30) is accepted"}


def find_java_bin() -> str:
    cands = []
    if os.environ.get("JAVA_HOME"):
        cands.append(Path(os.environ["JAVA_HOME"]) / "bin")
    cands += [Path(p).parent for p in glob.glob(str(TOOLS / "jre-*" / "*" / "bin" / "java*")) + glob.glob(str(TOOLS / "jdk-*" / "*" / "bin" / "java*"))]
    w = shutil.which("java")
    if w:
        cands.append(Path(w).parent)
    for c in cands:
        if (c / "java.exe").exists() or (c / "java").exists():
            return str(c)
    return ""


def find_jmeter() -> str:
    if os.environ.get("JMETER_HOME"):
        cands = [Path(os.environ["JMETER_HOME"]) / "bin"]
    else:
        cands = [Path(p) for p in glob.glob(str(TOOLS / "apache-jmeter-*" / "bin"))]
    for b in cands:
        for n in ("jmeter.bat", "jmeter"):
            if (b / n).exists() and (os.name == "nt") == n.endswith(".bat"):
                return str(b / n)
    return shutil.which("jmeter") or ""


def pct(sorted_vals: List[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    k = max(0, min(len(sorted_vals) - 1, math.ceil(p / 100 * len(sorted_vals)) - 1))
    return sorted_vals[k]


def parse_jtl(path: Path) -> Dict[str, dict]:
    rows: Dict[str, list] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.setdefault(r["label"], []).append(r)
    out = {}
    for label, rs in rows.items():
        el = sorted(float(r["elapsed"]) for r in rs)
        ts = [int(r["timeStamp"]) for r in rs]
        errs = [r for r in rs if r["success"].lower() != "true"]
        span = max(1.0, (max(ts) - min(ts)) / 1000.0)
        codes: Dict[str, int] = {}
        for r in rs:
            codes[r["responseCode"]] = codes.get(r["responseCode"], 0) + 1
        out[label] = {"samples": len(rs), "errors": len(errs), "error_pct": round(100 * len(errs) / len(rs), 2),
                      "avg_ms": round(sum(el) / len(el), 1), "p50_ms": pct(el, 50), "p90_ms": pct(el, 90), "p95_ms": pct(el, 95),
                      "p99_ms": pct(el, 99), "max_ms": el[-1], "tps": round(len(rs) / span, 2), "response_codes": codes,
                      "first_error": (errs[0]["responseCode"] + " " + " ".join(errs[0]["failureMessage"].replace("*", " ").split())[:110]) if errs else ""}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Real Apache JMeter load test")
    ap.add_argument("--profile", choices=list(PROFILES), default="standard")
    ap.add_argument("--master", default=MASTER_EMAIL)
    ap.add_argument("--master-id", default=MASTER_ID)
    ap.add_argument("--prefix", default=DEFAULT_PREFIX)
    ap.add_argument("--domain", default=DEFAULT_DOMAIN)
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int, default=FOLLOWER_COUNT)
    ap.add_argument("--instance", default="paper")
    ap.add_argument("--sla", action="append", default=[], help='override p95 budget, e.g. --sla "ORDER place market=3000"')
    ap.add_argument("--i-understand-real-money", action="store_true")
    a = ap.parse_args()
    if a.instance != "paper" and not a.i_understand_real_money:
        print("Refusing to load-test a non-paper instance without --i-understand-real-money")
        return 2
    for s in a.sla:
        k, _, v = s.rpartition("=")
        SLA_P95_MS[k] = float(v)

    jmeter, java_bin = find_jmeter(), find_java_bin()
    if not jmeter or not java_bin:
        print("Apache JMeter / Java not found.  Install once with:  python scripts/install_jmeter.py")
        return 2
    if not PLAN.exists():
        print(f"Plan missing: {PLAN}  (python tests/jmeter/build_plan.py)")
        return 2

    prof = PROFILES[a.profile]
    emails = [f"{a.prefix}{i}@{a.domain}" for i in range(a.start, a.end + 1)]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = BASE_DIR / "reports" / "jmeter" / ts
    run_dir.mkdir(parents=True, exist_ok=True)
    jtl, html = run_dir / "results.jtl", run_dir / "html"

    print("=" * 80)
    print(f" REAL APACHE JMETER LOAD TEST | profile={a.profile} | instance={a.instance} | followers={len(emails)}")
    print("=" * 80)
    c = BlackTraderClient(base_url=BASE_URL, max_workers=10)
    print("[*] Clean slate ...")
    c.teardown_all_accounts(a.master, emails, a.instance)

    secrets_dir = Path(tempfile.mkdtemp(prefix="btjm_"))
    secrets = []
    try:
        print("[*] Creating auth tokens (kept only in a temp dir) ...")
        master_token = c.get_trader_token(a.master)
        token_followers = emails[:prof["tokens"]]
        rows = []
        for e in token_followers:
            rows.append(f"{e},{c.get_trader_token(e)}")
        csv_path = secrets_dir / "followers.csv"
        csv_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
        props = secrets_dir / "secret.properties"
        props.write_text(f"MASTER_TOKEN={master_token}\nMEMBER_PASSWORD={MEMBER_PASSWORD}\nFOLLOWERS_CSV={csv_path.as_posix()}\n", encoding="utf-8")
        secrets = [master_token, MEMBER_PASSWORD] + [r.split(",", 1)[1] for r in rows]

        host = BASE_URL.split("://", 1)[1].split("/")[0]
        proto = BASE_URL.split("://", 1)[0]
        cmd = [jmeter, "-n", "-t", str(PLAN), "-q", str(props), "-l", str(jtl), "-j", str(run_dir / "jmeter.log"), "-e", "-o", str(html),
               f"-JHOST={host.split(':')[0]}", f"-JPORT={host.split(':')[1] if ':' in host else ('443' if proto == 'https' else '80')}",
               f"-JPROTOCOL={proto}", f"-JINSTANCE={a.instance}"] + [f"-J{k}={v}" for k, v in prof.items() if k != "tokens"]
        env = dict(os.environ, JAVA_HOME=str(Path(java_bin).parent), PATH=java_bin + os.pathsep + os.environ.get("PATH", ""),
                   JVM_ARGS="-Xms512m -Xmx1g")
        print(f"[*] Launching JMeter ({Path(jmeter).name}) - plan {PLAN.name}")
        t0 = time.time()
        proc = subprocess.run(cmd, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, cwd=str(run_dir))
        dur = time.time() - t0
        tail = [l for l in proc.stdout.splitlines() if "summary" in l.lower() or "Err:" in l][-6:]
        print("\n".join(tail))
        print(f"[*] JMeter finished in {dur:.0f}s (exit {proc.returncode})")
    finally:
        shutil.rmtree(secrets_dir, ignore_errors=True)

    # never leave a credential in a log we keep
    for f in run_dir.glob("*.log"):
        t = f.read_text(encoding="utf-8", errors="replace")
        for s in secrets:
            if s and len(s) > 5:
                t = t.replace(s, "***")
        f.write_text(t, encoding="utf-8")

    results = []
    if not jtl.exists() or jtl.stat().st_size == 0:
        print("[FAIL] JMeter produced no results. Output:\n" + proc.stdout[-1500:] + proc.stderr[-800:])
        return 1
    stats = parse_jtl(jtl)

    print("\n" + "-" * 80)
    print(f"{'request':<26}{'n':>6}{'err%':>7}{'avg':>8}{'p50':>8}{'p95':>8}{'p99':>8}{'max':>8}{'tps':>7}")
    for label, s in sorted(stats.items()):
        print(f"{label:<26}{s['samples']:>6}{s['error_pct']:>7}{s['avg_ms']:>8.0f}{s['p50_ms']:>8.0f}{s['p95_ms']:>8.0f}{s['p99_ms']:>8.0f}{s['max_ms']:>8.0f}{s['tps']:>7}")
    print("-" * 80)

    for label, s in sorted(stats.items()):
        if label.startswith("CLEANUP"):
            continue
        if label.startswith("NEG "):
            ok = s["errors"] == 0
            known = KNOWN_BUG_LABELS.get(label, "")
            res = {"name": f"Validation: {label[4:]}", "status": "PASS" if ok else "FAIL", "metrics": s}
            if not ok:
                res["finding"] = (f"KNOWN PLATFORM BUG - {known}. " if known else "") + f"got {s['first_error']}"
            print(f"[{res['status']}] {res['name']}" + (f"  <- {res['finding']}" if not ok else ""))
        else:
            sla = SLA_P95_MS.get(label)
            reasons = []
            if s["error_pct"] > MAX_ERROR_PCT:
                reasons.append(f"error rate {s['error_pct']}% > {MAX_ERROR_PCT}% ({s['first_error']})")
            if sla and s["p95_ms"] > sla:
                reasons.append(f"p95 {s['p95_ms']:.0f}ms > SLA {sla:.0f}ms")
            res = {"name": f"Load: {label}", "status": "FAIL" if reasons else "PASS", "sla_p95_ms": sla, "metrics": s}
            if reasons:
                res["finding"] = "; ".join(reasons)
            print(f"[{res['status']}] {res['name']}: {s['samples']} req, err {s['error_pct']}%, p95 {s['p95_ms']:.0f}ms (SLA {sla})"
                  + (f"  <- {res['finding']}" if reasons else ""))
        results.append(res)

    # ---- integrity audit: every copied position must be closed after the load ----
    print("\n[*] Post-load integrity audit (waiting 5s for fan-out to settle) ...")
    time.sleep(5)
    allm = [a.master] + emails
    pos = c.fetch_all_followers_positions(allm, instance=a.instance)
    orphans = {e: d.get("count", 0) for e, d in pos.items() if d.get("count", 0)}
    margin = {e: d["funds"].get("used_margin") for e, d in pos.items() if d.get("funds") and abs(float(d["funds"].get("used_margin") or 0)) > 0.01}
    # capture WHAT was left behind and when it opened relative to the master's closes (open/close race evidence)
    close_ends = sorted(int(r["timeStamp"]) + int(float(r["elapsed"])) for r in csv.DictReader(open(jtl, newline="", encoding="utf-8"))
                        if r["label"] == "ORDER close position")
    details = []
    for e in orphans:
        for p in pos[e].get("positions", []):
            try:
                opened = int(datetime.fromisoformat(p["opened_at"].replace("Z", "+00:00")).timestamp() * 1000)
            except Exception:
                opened = None
            prev = [c_ for c_ in close_ends if opened and c_ <= opened]
            nxt = [c_ for c_ in close_ends if opened and c_ > opened]
            details.append({"account": e, "market_order_id": p.get("market_order_id"), "side": p.get("side"), "qty": p.get("net_qty"),
                            "opened_at": p.get("opened_at"), "ms_after_last_master_close": (opened - prev[-1]) if prev else None,
                            "ms_before_next_master_close": (nxt[0] - opened) if nxt else None,
                            "master_closes_after_it_opened": len(nxt)})
    for d in details[:6]:
        print("      orphan:", d)
    audit = {"name": "Integrity: no orphan positions / stuck margin after load", "status": "FAIL" if (orphans or margin) else "PASS",
             "metrics": {"accounts": len(allm), "accounts_with_open_positions": len(orphans), "open_positions": sum(orphans.values()),
                         "accounts_with_stuck_margin": len(margin), "orphan_details": details[:20]}}
    if orphans or margin:
        audit["finding"] = (f"{len(orphans)} accounts still hold {sum(orphans.values())} positions after the master closed everything; "
                            f"{len(margin)} with stuck margin; e.g. {dict(list(orphans.items())[:3])}")
    print(f"[{audit['status']}] {audit['name']}" + (f"  <- {audit['finding']}" if audit.get("finding") else ""))
    results.append(audit)
    print("[*] Teardown ...")
    c.teardown_all_accounts(a.master, emails, a.instance)

    # ---- evidence ----
    ev = BASE_DIR / "reports" / "evidence"
    ev.mkdir(parents=True, exist_ok=True)
    jp, mp = ev / f"jmeter_real_evidence_{ts}.json", ev / f"jmeter_real_evidence_{ts}.md"
    ver = "5.6.3"
    jp.write_text(json.dumps({"suite": "Apache JMeter load test", "jmeter_version": ver, "timestamp": datetime.now(timezone.utc).isoformat(),
                              "profile": a.profile, "profile_settings": prof, "instance": a.instance, "followers": len(emails),
                              "duration_sec": round(dur), "sla_p95_ms": SLA_P95_MS, "html_dashboard": str(html / "index.html"),
                              "results": results}, indent=2, default=str), encoding="utf-8")
    icon = {"PASS": "✅", "FAIL": "❌"}
    md = [f"# Apache JMeter Load Test ({a.profile})", "", f"**JMeter {ver}** | instance `{a.instance}` | {len(emails)} followers | {dur:.0f}s  ",
          f"**HTML dashboard:** `{html / 'index.html'}`", "",
          "| Request | Result | Samples | Err % | p50 ms | p95 ms | p99 ms | TPS | SLA p95 |", "| :--- | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for r in results:
        m = r["metrics"]
        if "p95_ms" in m:
            md.append(f"| {r['name']} | {icon[r['status']]} | {m['samples']} | {m['error_pct']} | {m['p50_ms']:.0f} | {m['p95_ms']:.0f} | {m['p99_ms']:.0f} | {m['tps']} | {r.get('sla_p95_ms') or '-'} |")
        else:
            md.append(f"| {r['name']} | {icon[r['status']]} | - | - | - | - | - | - | - |")
    md += ["", "## Findings", ""] + [f"- **{r['name']}** - {r['finding']}" for r in results if r.get("finding")]
    mp.write_text("\n".join(md) + "\n", encoding="utf-8")

    failed = [r for r in results if r["status"] == "FAIL"]
    print("\n" + "=" * 80)
    print(f" RESULT: {len(results) - len(failed)}/{len(results)} checks passed")
    print(f" Evidence: {mp}\n HTML dashboard: {html / 'index.html'}")
    print("=" * 80)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
