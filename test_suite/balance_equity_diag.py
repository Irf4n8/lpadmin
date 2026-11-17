#!/usr/bin/env python3
"""Diagnose balance/equity sizing: 10 master BUY market orders, compare every follower's positions with
expected = master_lot * follower_balance / master_balance using the ACTUAL balances from the admin API.
Usage: python test_suite/balance_equity_diag.py --i-understand-real-money [--modes balance,equity] [--n 100]"""
import sys, time, json, argparse
from collections import Counter
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import test_suite.go_live_spec_runner as g
from test_suite.go_live_spec_runner import *  # noqa
ap = argparse.ArgumentParser(); ap.add_argument("--i-understand-real-money", action="store_true")
ap.add_argument("--modes", default="balance,equity"); ap.add_argument("--n", type=int, default=100); ap.add_argument("--orders", type=int, default=10)
ap.add_argument("--lot", type=float, default=0.1)
A = ap.parse_args()
if not A.i_understand_real_money: sys.exit("needs --i-understand-real-money")
for m in c.get_admin_members(): g.MEMBERS[m.get("email")] = m.get("member_id")
g.MID = c.get_copy_followers(M, I)[0]["master_client_id"]
FS = ALL[:A.n]; OUT = {}
def bal(e): 
    return {m["email"]: (m.get("balances") or {}).get("real", 0) for m in c.get_admin_members()}
for mode in A.modes.split(","):
    print(f"\n=== {mode} ===", flush=True); clean(FS)
    g.setbal(M, 100e6)
    for i, f in enumerate(FS): g.setbal(f, 100e6 * (1, 2, 3, 0.5)[i * 4 // len(FS)])
    for f in FS: c.follow_master(f, g.MID, I, mode, 1.0)
    time.sleep(3)
    b = bal(None); mb = b[M]
    acc = 0
    for _ in range(A.orders):
        r = buy(q=A.lot); acc += r['status_code'] == 200; time.sleep(0.08)
    print(f'  master accepted {acc}/{A.orders}')
    time.sleep(6)
    rows = []; cats = Counter()
    for f in FS:
        ps = [p for p in pos(f) if p["side"] == "BUY"]; exp = A.lot * b[f] / mb
        qs = sorted(round(p["net_qty"], 6) for p in ps)
        right = [q for q in qs if abs(q - exp) <= max(0.0011, exp * 0.01)]
        if len(ps) == acc and len(right) == len(ps): k = "OK"
        elif len(ps) < acc and len(right) == len(ps): k = "MISSING_COPIES (sizes right)"
        elif len(ps) == acc: k = "WRONG_SIZE"
        else: k = "MISSING+WRONG_SIZE"
        cats[k] += 1; rows.append({"f": f, "bal_ratio": round(b[f] / mb, 4), "n_pos": len(ps), "expected_qty": round(exp, 6), "qtys": Counter(qs), "cat": k})
    print(f"  master balance {mb:,.0f}; followers {len(FS)}; categories: {dict(cats)}")
    for r in [x for x in rows if x["cat"] != "OK"][:6]: print("   ", r["f"].split("@")[0], "ratio", r["bal_ratio"], "positions", r["n_pos"], "want qty", r["expected_qty"], "got", dict(r["qtys"]))
    OUT[mode] = {"summary": dict(cats), "rows": [{**r, "qtys": dict(r["qtys"])} for r in rows]}
    clean(FS)
for f in FS: follow(f, "multiplier", 2.0)
p = ROOT / "reports" / "evidence" / f"balance_equity_diag_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
p.write_text(json.dumps(OUT, indent=1, default=str)); print("evidence:", p)
