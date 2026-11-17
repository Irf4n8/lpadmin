#!/usr/bin/env python3
"""
Real-only toolkit for a master + followers on COPY, MAM or PAMM
================================================================
Standalone (needs only `requests`).  Works for any master / follower set, so a colleague can run it on
their own accounts.  Everything is READ-ONLY unless you pass --apply.

  check      links + wallets + open positions for the master and every follower (read-only)
  fund-only  fund ONE instance on all accounts and set the other three wallets to 0,
             then read all four wallets back and report any account that does not match
             (dry-run unless --apply; --flatten closes open positions + cancels orders first)

Instances: paper, paper-net (practice) and real, real-net (real money; hedging / netting).

Config (flags or environment variables):
  BASE_URL, ADMIN_EMAIL, ADMIN_PASSWORD, MEMBER_PASSWORD, MASTER_EMAIL,
  FOLLOWER_PREFIX (default follower), FOLLOWER_DOMAIN, FOLLOWER_COUNT (default 100)

Examples
  python social_real_only.py check --kind mam
  python social_real_only.py fund-only --instance real                  # dry run
  python social_real_only.py fund-only --instance real --flatten --apply --type-confirm REAL
"""
import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests

INSTANCES = ("paper", "paper-net", "real", "real-net")
DEFAULT_FUNDS = {"paper": 1_000_000.0, "paper-net": 1_000_000.0, "real": 100_000_000.0, "real-net": 1_000_000.0}
PRACTICE_MAX = 10_000_000.0
TIMEOUT = 30


def env(name, default=""):
    return os.environ.get(name, default)


class Platform:
    def __init__(self, base, admin_email, admin_pw, member_pw):
        self.base, self.admin_email, self.admin_pw, self.member_pw = base.rstrip("/"), admin_email, admin_pw, member_pw
        self._admin = None
        self._tok = {}

    # ---- auth -------------------------------------------------------------
    def admin_headers(self):
        if not self._admin:
            r = requests.post(f"{self.base}/admin/api/login", json={"email": self.admin_email, "password": self.admin_pw, "remember": True}, timeout=TIMEOUT)
            if r.status_code != 200:
                sys.exit(f"Admin login failed: HTTP {r.status_code}")
            self._admin = r.json()["token"]
        return {"Authorization": f"Bearer {self._admin}", "Content-Type": "application/json"}

    def trader_headers(self, email, instance):
        if email not in self._tok:
            s = requests.Session()                                   # own session: no cookie races between threads
            r = s.post(f"{self.base}/api/auth/login", json={"email": email, "password": self.member_pw}, timeout=TIMEOUT)
            if r.status_code != 200:
                raise RuntimeError(f"login failed for {email}: HTTP {r.status_code}")
            t = s.post(f"{self.base}/api/auth/chart-token", timeout=TIMEOUT)
            if t.status_code != 200:
                raise RuntimeError(f"chart-token failed for {email}: HTTP {t.status_code}")
            self._tok[email] = t.json().get("token") or t.json().get("access_token")
        return {"Authorization": f"Bearer {self._tok[email]}", "X-Broker-ID": instance, "Content-Type": "application/json"}

    # ---- calls ------------------------------------------------------------
    def members(self):
        r = requests.get(f"{self.base}/admin/api/members", headers=self.admin_headers(), timeout=TIMEOUT)
        r.raise_for_status()
        return r.json().get("members", [])

    def set_balance(self, member_id, instance, amount):
        r = requests.post(f"{self.base}/admin/api/members/{member_id}/balance", headers=self.admin_headers(), timeout=TIMEOUT,
                          json={"instance": instance, "balance": amount, "remark": "social_real_only", "force": True})
        return r.status_code, (r.text[:80] if r.status_code != 200 else "")

    def oms(self, email, method, path, instance="real", body=None):
        r = requests.request(method, f"{self.base}/v1/oms/{instance}{path}", headers=self.trader_headers(email, instance), json=body, timeout=TIMEOUT)
        try:
            data = r.json()
        except ValueError:
            data = r.text
        return r.status_code, data

    def flatten(self, email, instance):
        code, d = self.oms(email, "GET", "/positions", instance)
        ids = [p.get("market_order_id") or p.get("order_id") for p in (d.get("positions") or [])] if code == 200 and isinstance(d, dict) else []
        if ids:
            self.oms(email, "POST", "/positions/bulk/squareoff", instance, {"market_order_ids": ids})
        code, d = self.oms(email, "GET", "/orders", instance)
        pend = [o.get("order_id") for o in (d.get("orders") or []) if o.get("state") in ("PENDING", "OPEN", "NEW", "WORKING")] if code == 200 and isinstance(d, dict) else []
        if pend:
            self.oms(email, "POST", "/orders/bulk/cancel", instance, {"order_ids": pend})
        return len(ids), len(pend)


def accounts(a):
    return [a.master] + [f"{a.prefix}{i}@{a.domain}" for i in range(1, a.count + 1)]


# =============================================================================
def cmd_check(p, a):
    emails = accounts(a)
    print(f"[*] {a.kind.upper()} master {a.master} + {a.count} followers  @ {p.base}\n")
    # links, from the master's point of view
    _, d = p.oms(a.master, "GET", f"/{a.kind}/follows", "real")
    if isinstance(d, dict):
        links = d.get("followers") or d.get("pool") or d.get("subscriptions") or []
        print(f"[links] is_master={d.get('is_master')}  entries={len(links)}  ({', '.join(k for k in ('followers', 'pool', 'subscriptions') if k in d)})")
        by_inst = {}
        for l in links:
            by_inst[(l.get("instance"), l.get("status"))] = by_inst.get((l.get("instance"), l.get("status")), 0) + 1
        for (inst, st), n in sorted(by_inst.items(), key=lambda x: str(x)):
            print(f"        {inst or '-'} / {st or '-'}: {n}")
        if d.get("master_blocked_reason"):
            print(f"        note: {d['master_blocked_reason']}")
    # wallets
    by_email = {m["email"].lower(): m for m in p.members()}
    print("\n[wallets] accounts per balance")
    for inst in INSTANCES:
        vals = {}
        for e in emails:
            b = (by_email.get(e.lower(), {}).get("balances") or {}).get(inst)
            vals[None if b is None else round(b)] = vals.get(None if b is None else round(b), 0) + 1
        print(f"        {inst:10} " + ", ".join(f"{k}: {n}" for k, n in sorted(vals.items(), key=lambda x: (x[0] is None, x[0] or 0))[:4]))
    missing = [e for e in emails if e.lower() not in by_email]
    print(f"\n[accounts] found {len(emails) - len(missing)}/{len(emails)}" + (f"  missing: {missing[:5]}" if missing else ""))

    # open positions per instance
    def pos(e):
        out = {}
        for inst in INSTANCES:
            try:
                code, d = p.oms(e, "GET", "/positions", inst)
                n = len(d.get("positions") or []) if code == 200 and isinstance(d, dict) else 0
            except Exception:
                n = -1
            if n:
                out[inst] = n
        return e, out
    with ThreadPoolExecutor(8) as ex:
        res = [r for r in ex.map(pos, emails) if r[1]]
    print(f"[positions] accounts with open positions: {len(res)}" + "".join(f"\n        {e.split('@')[0]}: {o}" for e, o in res[:10]))
    return 0


def cmd_fund_only(p, a):
    inst = a.instance
    amount = a.amount if a.amount is not None else DEFAULT_FUNDS[inst]
    if amount <= 0:
        sys.exit("--amount must be greater than 0")
    if inst.startswith("paper") and amount > PRACTICE_MAX:
        sys.exit(f"practice funds are capped at {PRACTICE_MAX:,.0f}")
    emails = accounts(a)
    wanted = {k: (amount if k == inst else 0.0) for k in INSTANCES}
    print(f"[plan] {len(emails)} accounts: {inst} = {amount:,.0f}; zero: {', '.join(k for k in INSTANCES if k != inst)}" + ("  (flatten first)" if a.flatten else ""))
    if not a.apply:
        print("[dry-run] nothing changed. Re-run with --apply (and --type-confirm REAL) to do it.")
        return 0
    if a.type_confirm != "REAL":
        sys.exit("This overwrites real-money wallets. Add:  --type-confirm REAL")
    if a.flatten:
        def fl(e):
            n = 0
            for k in INSTANCES:
                try:
                    c, o = p.flatten(e, k)
                    n += c + o
                except Exception:
                    pass
            return n
        with ThreadPoolExecutor(8) as ex:
            print(f"[flatten] closed/cancelled {sum(ex.map(fl, emails))} items")
        time.sleep(2)
    ids = {m["email"].lower(): m["member_id"] for m in p.members()}
    errors = {e: [] for e in emails}

    def fund(e):
        mid = ids.get(e.lower())
        if not mid:
            errors[e].append("member not found")
            return
        for k, v in wanted.items():
            code, msg = p.set_balance(mid, k, v)
            if code != 200:
                errors[e].append(f"{k}: HTTP {code} {msg}")
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(fund, emails))
    after = {m["email"].lower(): (m.get("balances") or {}) for m in p.members()}
    bad = 0
    for e in emails:                                                  # never trust the 200: read all four wallets back
        for k, v in wanted.items():
            got = after.get(e.lower(), {}).get(k)
            if got is None or abs(float(got) - v) > max(1.0, v * 1e-6):
                errors[e].append(f"{k}: read-back {got}, expected {v:g}")
        if errors[e]:
            bad += 1
            print(f"  [FAIL] {e}: {'; '.join(errors[e])[:160]}")
    print(f"[done] {len(emails) - bad}/{len(emails)} accounts verified: {inst}={amount:,.0f}, others=0")
    return 0 if not bad else 2


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["check", "fund-only"])
    ap.add_argument("--kind", choices=["copy", "mam", "pamm"], default="copy")
    ap.add_argument("--base-url", default=env("BASE_URL", "https://lpadmin.blackfx.com"))
    ap.add_argument("--admin-email", default=env("ADMIN_EMAIL"))
    ap.add_argument("--admin-password", default=env("ADMIN_PASSWORD"))
    ap.add_argument("--member-password", default=env("MEMBER_PASSWORD"))
    ap.add_argument("--master", default=env("MASTER_EMAIL"))
    ap.add_argument("--prefix", default=env("FOLLOWER_PREFIX", "follower"))
    ap.add_argument("--domain", default=env("FOLLOWER_DOMAIN", "mailinator.com"))
    ap.add_argument("--count", type=int, default=int(env("FOLLOWER_COUNT", "100")))
    ap.add_argument("--instance", choices=INSTANCES, default="real")
    ap.add_argument("--amount", type=float, default=None, help="balance for the chosen instance (default per instance)")
    ap.add_argument("--flatten", action="store_true", help="close positions / cancel orders before changing wallets")
    ap.add_argument("--apply", action="store_true", help="really change things (default is a dry run)")
    ap.add_argument("--type-confirm", default="", help="type REAL to overwrite real-money wallets")
    a = ap.parse_args()
    missing = [n for n, v in (("ADMIN_EMAIL", a.admin_email), ("ADMIN_PASSWORD", a.admin_password), ("MEMBER_PASSWORD", a.member_password), ("MASTER_EMAIL", a.master)) if not v]
    if missing:
        sys.exit("Missing: " + ", ".join(missing) + "  (set as environment variables or flags)")
    p = Platform(a.base_url, a.admin_email, a.admin_password, a.member_password)
    sys.exit({"check": cmd_check, "fund-only": cmd_fund_only}[a.command](p, a))


if __name__ == "__main__":
    main()
