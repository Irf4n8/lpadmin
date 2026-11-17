#!/usr/bin/env python3
"""Empirical probe: how does each copy mode size a follower's copy? (staging real/hedging, followers 1..12)"""
import sys, time, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import test_suite.go_live_spec_runner as g
from test_suite.go_live_spec_runner import *  # noqa
from test_suite.breakpoint_race_runner import funds
for m in c.get_admin_members(): g.MEMBERS[m.get("email")] = m.get("member_id")
g.MID = c.get_copy_followers(M, I)[0]["master_client_id"]
FS = ALL[:12]; clean(FS)
mb = 100e6; g.setbal(M, mb)
# (follower idx, mode, multiplier sent, balance ratio vs master, reverse)
plan = [("multiplier", .5, None, 0), ("multiplier", 1, None, 0), ("multiplier", 2, None, 0), ("multiplier", 1, None, 1),
        ("balance", 1, 1, 0), ("balance", 1, 2, 0), ("balance", 3, 2, 0), ("balance", 1, .5, 0), ("balance", 1, .3333, 0),
        ("equity", 1, 1, 0), ("equity", 1, 2, 0), ("equity", 3, 2, 0)]
for f, (mode, mult, br, rev) in zip(FS, plan):
    if br: g.setbal(f, mb * br)
    c.follow_master(f, g.MID, I, mode, mult, reverse=bool(rev))
time.sleep(3)
mf = funds(c, M, I)
LOT = 0.1
r = buy(q=LOT); time.sleep(6)
mf2 = funds(c, M, I)
print("master funds before", mf, "after", mf2)
print(f"{'mode':10s} {'mult':>5s} {'rev':>3s} {'bal/master':>11s} {'eq/master':>10s} -> follower qty (master {LOT})  qty/master_lot")
for f, (mode, mult, br, rev) in zip(FS, plan):
    ff = funds(c, f, I); ps = pos(f); q = sum(p["net_qty"] * (1 if p["side"] == "BUY" else -1) for p in ps)
    print(f"{mode:10s} {mult:5g} {rev:3d} {ff['balance']/mf['balance']:11.4f} {ff['equity']/mf['equity']:10.4f} -> {q:+.4f}   x{q/LOT:+.4f}")
clean(FS)
for f in FS: follow(f, "multiplier", 2.0)
