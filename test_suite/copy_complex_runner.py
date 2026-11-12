#!/usr/bin/env python3
"""
Complex Copy-Trading Scenario Suite
===================================
Model-based tests: followers are split into COHORTS with different copy rules and, after every
master action, each follower's net signed quantity is compared with what the model predicts:

    expected_follower_net = master_net * factor
    factor = multiplier (multiplier mode) | balance ratio | equity ratio | -multiplier (reverse)

Scenarios
---------
X1  Mixed-mode sizing        multiplier / balance / equity / reverse cohorts side by side
X2  Reverse lifecycle        reverse followers open the opposite side and close with the master
X3  Pyramid + partial cascade  adds, partial reduces, hedge legs, single closes - checked after every step
X4  Protection sync          TP/SL set and modified 3x on master -> identical triggers on followers
X5  Follower intervention    follower closes its copy / trades on its own -> isolation holds
X6  Multiplier change mid-trade  existing position untouched, next order uses the new multiplier
X7  Phantom-copy check       far pending orders placed and cancelled -> no positions or leftover pendings on followers
X8  Open/close churn         rapid open+close cycles -> everyone flat, no stuck margin
X9  Chained concurrent ops   protection + reduce + two new orders fired simultaneously
X10 Seeded random walk       random open/reduce/close/protect sequence, model-checked (reproduce with --seed)

Severity:  HIGH = model violated (bug)   MED = suspicious / unsupported behaviour   INFO = measurement
Paper instance only unless --i-understand-real-money.

Usage:
    python test_suite/copy_complex_runner.py --end 20
    python test_suite/copy_complex_runner.py --only X3,X10 --seed 99
"""

import argparse
import json
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config.settings import BASE_URL, DEFAULT_PREFIX, DEFAULT_DOMAIN, MASTER_EMAIL, MASTER_ID, FOLLOWER_COUNT
from test_suite.baseline import get_expected_multiplier
from test_suite.breakpoint_race_runner import Findings, funds, getf, is_5xx, mkt_id, parallel, pos_qty
from test_suite.client import BlackTraderClient

SYM = "BINANCE:BTCUSDT.P"
PATTERN = ["M2", "M2", "M1", "M1", "M05", "BAL", "BAL", "EQ", "REV", "REV"]
BAL_FACTORS = [0.5, 2.0, 0.1]
EQ_FACTORS = [0.25, 4.0]


class Ctx:
    def __init__(self, c, master, master_id, emails, inst, first_index):
        self.c, self.master, self.master_id, self.emails, self.inst, self.first = c, master, master_id, emails, inst, first_index
        self.cohort: Dict[str, str] = {}
        self.factor: Dict[str, float] = {}
        self.orig_balance: Dict[str, float] = {}
        self.member_id: Dict[str, str] = {}
        self.max_lag = 0.0

    def of(self, cohort: str) -> List[str]:
        return [e for e in self.emails if self.cohort[e] == cohort]


def signed(positions: List[dict]) -> float:
    return sum((1 if p.get("side") == "BUY" else -1) * pos_qty(p) for p in positions if p.get("symbol") == SYM)


def master_positions(x: Ctx) -> List[dict]:
    return x.c.get_positions(x.master, x.inst).get("positions", [])


def setup_cohorts(x: Ctx):
    c, inst = x.c, x.inst
    m_funds = funds(c, x.master, inst)
    m_bal, m_eq = m_funds["balance"], m_funds["equity"]
    members = {m.get("email"): m for m in c.get_admin_members()}
    bi = ei = 0
    for i, e in enumerate(x.emails):
        coh = PATTERN[i % len(PATTERN)]
        x.cohort[e] = coh
        mem = members.get(e, {})
        x.member_id[e] = getf(mem, "member_id", "client_id", "id")
        if coh in ("BAL", "EQ"):
            x.orig_balance[e] = funds(c, e, inst)["balance"]
            ratio = BAL_FACTORS[bi % 3] if coh == "BAL" else EQ_FACTORS[ei % 2]
            bi, ei = (bi + 1, ei) if coh == "BAL" else (bi, ei + 1)
            if x.member_id[e]:
                c.set_member_balance(x.member_id[e], round(m_bal * ratio, 2), inst)
    time.sleep(1.0)

    def join(e):
        coh = x.cohort[e]
        if coh == "M2":
            return c.follow_master(e, x.master_id, inst, method="multiplier", multiplier=2.0)
        if coh == "M1":
            return c.follow_master(e, x.master_id, inst, method="multiplier", multiplier=1.0)
        if coh == "M05":
            return c.follow_master(e, x.master_id, inst, method="multiplier", multiplier=0.5)
        if coh == "REV":
            return c.follow_master(e, x.master_id, inst, method="multiplier", multiplier=1.0, reverse=True)
        return c.follow_master(e, x.master_id, inst, method="balance" if coh == "BAL" else "equity", multiplier=1.0)

    with ThreadPoolExecutor(max_workers=10) as ex:
        list(ex.map(join, x.emails))
    time.sleep(1.0)
    m_funds = funds(c, x.master, inst)
    for e in x.emails:
        coh = x.cohort[e]
        f = funds(c, e, inst)
        x.factor[e] = {"M2": 2.0, "M1": 1.0, "M05": 0.5, "REV": -1.0}.get(coh) or (
            f["balance"] / m_funds["balance"] if coh == "BAL" else f["equity"] / m_funds["equity"])
    print("[*] Cohorts:", {k: len(x.of(k)) for k in ("M2", "M1", "M05", "BAL", "EQ", "REV")})


def restore(x: Ctx):
    for e in x.emails:
        idx = x.first + x.emails.index(e)
        try:
            x.c.follow_master(e, x.master_id, x.inst, method="multiplier", multiplier=get_expected_multiplier(idx), reverse=False)
            if e in x.orig_balance and x.member_id.get(e):
                x.c.set_member_balance(x.member_id[e], x.orig_balance[e], x.inst)
        except Exception as ex:
            print(f"[!] restore failed for {e}: {ex}")


def reset(x: Ctx):
    x.c.teardown_all_accounts(x.master, x.emails, instance=x.inst)
    time.sleep(1.2)


def verify(x: Ctx, F: Findings, label: str, timeout: float = 14.0, only: List[str] = None) -> bool:
    """Compare every follower's net signed qty with master_net * factor; poll until converged."""
    t0 = time.time()
    targets = only or x.emails
    while True:
        mnet = signed(master_positions(x))
        data = x.c.fetch_all_followers_positions(targets, instance=x.inst)
        bad = []
        for e in targets:
            exp = mnet * x.factor[e]
            got = signed(data.get(e, {}).get("positions", []))
            if abs(got - exp) > max(2e-3, 0.01 * abs(exp)):
                bad.append((e, x.cohort[e], round(exp, 5), round(got, 5)))
        if not bad:
            x.max_lag = max(x.max_lag, time.time() - t0)
            print(f"    ok   {label}: master_net={mnet:+.4f}, {len(targets)} followers match the model ({time.time() - t0:.1f}s)")
            return True
        if time.time() - t0 > timeout:
            by = {}
            for _, coh, _, _ in bad:
                by[coh] = by.get(coh, 0) + 1
            F.add("HIGH", f"{label}: {len(bad)}/{len(targets)} followers off-model (by cohort {by}); "
                          f"e.g. {bad[0][0].split('@')[0]} [{bad[0][1]}] expected {bad[0][2]} got {bad[0][3]} (master net {mnet:+.4f})")
            return False
        time.sleep(0.6)


def buy(x, qty, side="BUY"):
    return x.c.place_order(x.master, symbol=SYM, side=side, qty=qty, instance=x.inst)


# ------------------------------------------------------------------------- scenarios
def x1_mixed_modes(x: Ctx, **_):
    print("\n[X1] Mixed-mode sizing")
    F = Findings("X1 Mixed-mode sizing")
    reset(x)
    F.metrics["factors"] = {k: sorted({round(x.factor[e], 3) for e in x.of(k)}) for k in ("M2", "M1", "M05", "BAL", "EQ", "REV")}
    buy(x, 1.0); verify(x, F, "BUY 1.0", )
    buy(x, 0.4, "SELL"); verify(x, F, "+ SELL 0.4 (hedge leg)")
    x.c.bulk_squareoff(x.master, x.inst); verify(x, F, "master flat")
    return F.result()


def x2_reverse(x: Ctx, **_):
    print("\n[X2] Reverse lifecycle")
    F = Findings("X2 Reverse lifecycle")
    reset(x)
    rev, base = x.of("REV"), x.of("M1")
    if not rev or not base:
        F.add("INFO", "needs REV and M1 cohorts"); return F.result("SKIP")
    b0 = {e: funds(x.c, e, x.inst)["balance"] for e in rev + base}
    m0 = funds(x.c, x.master, x.inst)["balance"]
    mid = mkt_id(buy(x, 1.0))
    verify(x, F, "master BUY 1.0 -> reverse SELL", only=rev + base)
    sides = {x.c.get_positions(e, x.inst)["positions"][0]["side"] for e in rev if x.c.get_positions(e, x.inst).get("positions")}
    if sides != {"SELL"}:
        F.add("HIGH", f"reverse followers hold sides {sides}, expected only SELL")
    time.sleep(2.0)
    x.c.squareoff_position(x.master, mid, x.inst)
    verify(x, F, "after master close", only=rev + base)
    time.sleep(1.0)
    dm = funds(x.c, x.master, x.inst)["balance"] - m0
    drev = sum(funds(x.c, e, x.inst)["balance"] - b0[e] for e in rev) / len(rev)
    dbase = sum(funds(x.c, e, x.inst)["balance"] - b0[e] for e in base) / len(base)
    F.metrics.update(master_pnl=round(dm, 4), avg_normal_follower_pnl=round(dbase, 4), avg_reverse_follower_pnl=round(drev, 4))
    if abs(dm) > 2.0 and (dm > 0) == (drev > 0):
        F.add("MED", f"reverse follower PnL ({drev:+.3f}) has the SAME sign as master ({dm:+.3f})")
    F.add("INFO", f"PnL master {dm:+.3f} | normal follower {dbase:+.3f} | reverse follower {drev:+.3f}")
    return F.result()


def x3_pyramid(x: Ctx, **_):
    print("\n[X3] Pyramid + partial cascade")
    F = Findings("X3 Pyramid + partial cascade")
    reset(x)
    a = mkt_id(buy(x, 1.0)); verify(x, F, "open A 1.0")
    b = mkt_id(buy(x, 0.5)); verify(x, F, "add B 0.5")
    x.c.reduce_position(x.master, a, 0.4, x.inst); verify(x, F, "reduce A by 0.4")
    c_ = mkt_id(buy(x, 0.25)); verify(x, F, "add C 0.25")
    x.c.reduce_position(x.master, b, 0.2, x.inst); verify(x, F, "reduce B by 0.2")
    d = mkt_id(buy(x, 0.3, "SELL")); verify(x, F, "hedge SELL D 0.3")
    x.c.squareoff_position(x.master, a, x.inst); verify(x, F, "close A")
    x.c.reduce_position(x.master, c_, 0.1, x.inst); verify(x, F, "reduce C by 0.1")
    x.c.bulk_squareoff(x.master, x.inst); verify(x, F, "close everything")
    return F.result()


def x4_protection(x: Ctx, **_):
    print("\n[X4] Protection sync (TP/SL set + modified)")
    F = Findings("X4 Protection sync")
    reset(x)
    peers = [e for e in x.emails if x.cohort[e] != "REV"]
    r_buy, r_sell = buy(x, 0.5), buy(x, 0.5, "SELL")
    mb, ms = mkt_id(r_buy), mkt_id(r_sell)
    px = float(r_buy["data"]["position"]["avg_entry_price"])
    verify(x, F, "open BUY + SELL legs", only=peers)

    def follower_trigger(e, side, key):
        for p in x.c.get_positions(e, x.inst).get("positions", []):
            if p.get("side") == side:
                return (p.get(key) or {}).get("trigger_price")
        return None

    for step, pct in enumerate((0.02, 0.03, 0.05), 1):
        tp_b, sl_b = round(px * (1 + pct), 1), round(px * (1 - pct), 1)
        tp_s, sl_s = round(px * (1 - pct), 1), round(px * (1 + pct), 1)
        x.c.set_position_protection(x.master, mb, tp=tp_b, sl=sl_b, instance=x.inst)
        x.c.set_position_protection(x.master, ms, tp=tp_s, sl=sl_s, instance=x.inst)
        want = {("BUY", "tp_order"): tp_b, ("BUY", "sl_order"): sl_b, ("SELL", "tp_order"): tp_s, ("SELL", "sl_order"): sl_s}
        t0, bad = time.time(), []
        while time.time() - t0 < 10:
            bad = [(e, k) for e in peers for k, v in want.items() if follower_trigger(e, *k) != v]
            if not bad:
                break
            time.sleep(0.8)
        if bad:
            who = sorted({e.split("@")[0] for e, _ in bad})
            F.add("HIGH", f"modify #{step}: {len(bad)} protection triggers on {len(who)}/{len(peers)} followers do not match master "
                          f"(e.g. {bad[0][0].split('@')[0]} {bad[0][1]} has {follower_trigger(bad[0][0], *bad[0][1])} want {want[bad[0][1]]})")
        else:
            print(f"    ok   modify #{step}: all {len(peers)} followers carry master's TP/SL ({time.time() - t0:.1f}s)")
    x.c.bulk_squareoff(x.master, x.inst)
    verify(x, F, "close all", only=peers)
    return F.result()


def x5_intervention(x: Ctx, **_):
    print("\n[X5] Follower intervention & isolation")
    F = Findings("X5 Follower intervention")
    reset(x)
    m1 = x.of("M1")
    if len(m1) < 2:
        F.add("INFO", "needs 2 M1 followers"); return F.result("SKIP")
    f1, f2 = m1[0], m1[1]
    buy(x, 1.0); verify(x, F, "master BUY 1.0", only=[f1, f2])
    p1 = x.c.get_positions(f1, x.inst)["positions"][0]["market_order_id"]
    r = x.c.squareoff_position(f1, p1, x.inst)
    if r["status_code"] != 200:
        F.add("HIGH", f"follower could not close its own copy: {r['data']}")
    own = mkt_id(x.c.place_order(f2, symbol=SYM, side="BUY", qty=0.2, instance=x.inst))
    buy(x, 0.3)
    time.sleep(3.5)
    q1 = signed(x.c.get_positions(f1, x.inst)["positions"])
    q2 = signed(x.c.get_positions(f2, x.inst)["positions"])
    F.metrics.update(f1_net_after_master_add=q1, f2_net=q2)
    if abs(q1 - 0.3) > 2e-3:
        F.add("HIGH", f"after manually closing its copy, follower should still copy NEW master trades: net {q1}, expected 0.3")
    if abs(q2 - (1.0 + 0.2 + 0.3)) > 2e-3:
        F.add("HIGH", f"follower with its own trade: net {q2}, expected 1.5 (1.0 copy + 0.2 own + 0.3 copy)")
    x.c.bulk_squareoff(x.master, x.inst)
    time.sleep(3.0)
    left = [p for p in x.c.get_positions(f2, x.inst)["positions"]]
    if len(left) != 1 or left[0].get("market_order_id") != own:
        F.add("HIGH", f"master close must leave follower's OWN trade intact; follower holds {[(p['market_order_id'], p['net_qty']) for p in left]}")
    if signed(x.c.get_positions(f1, x.inst)["positions"]) != 0:
        F.add("HIGH", "follower 1 not flat after master close")
    return F.result()


def x6_multiplier_change(x: Ctx, **_):
    print("\n[X6] Multiplier change mid-trade")
    F = Findings("X6 Multiplier change mid-trade")
    reset(x)
    m1 = x.of("M1")
    if not m1:
        F.add("INFO", "needs an M1 follower"); return F.result("SKIP")
    f = m1[0]
    a = mkt_id(buy(x, 1.0)); verify(x, F, "master BUY 1.0 @1x", only=[f])
    r = x.c.follow_master(f, x.master_id, x.inst, method="multiplier", multiplier=3.0)
    F.metrics["refollow_http"] = r["status_code"]
    time.sleep(1.5)
    q_after = signed(x.c.get_positions(f, x.inst)["positions"])
    if abs(q_after - 1.0) > 2e-3:
        F.add("MED", f"changing multiplier to 3x RE-SIZED the open position: {q_after} (expected untouched 1.0)")
    buy(x, 0.5)
    time.sleep(3.5)
    q = signed(x.c.get_positions(f, x.inst)["positions"])
    F.metrics["net_after_second_order"] = q
    if abs(q - (q_after + 1.5)) > 2e-3:
        F.add("MED", f"new master order 0.5 should copy as 1.5 at 3x; follower net went {q_after} -> {q}")
    x.c.squareoff_position(x.master, a, x.inst)
    time.sleep(2.5)
    left = signed(x.c.get_positions(f, x.inst)["positions"])
    F.add("INFO", f"after closing master's first position follower net is {left} (second position still open on master)")
    x.c.bulk_squareoff(x.master, x.inst); time.sleep(2.5)
    if signed(x.c.get_positions(f, x.inst)["positions"]) != 0:
        F.add("HIGH", "orphan quantity left on follower after master closed everything")
    x.c.follow_master(f, x.master_id, x.inst, method="multiplier", multiplier=1.0)
    return F.result()


def x7_phantom(x: Ctx, **_):
    print("\n[X7] Phantom-copy check (far pending orders)")
    F = Findings("X7 Phantom-copy check")
    reset(x)
    r = buy(x, 0.01)
    px = float(r["data"]["position"]["avg_entry_price"])
    x.c.bulk_squareoff(x.master, x.inst); time.sleep(2.0)
    ids = []
    for side, otype, mult in (("BUY", "LIMIT", 0.5), ("SELL", "LIMIT", 1.5), ("BUY", "STOP", 1.5), ("SELL", "STOP", 0.5)) * 2:
        rr = x.c.place_order(x.master, symbol=SYM, side=side, order_type=otype, qty=0.1, price=round(px * mult, 1), instance=x.inst)
        oid = (rr.get("data") or {}).get("order", {}).get("order_id") if isinstance(rr.get("data"), dict) else None
        if oid:
            ids.append(oid)
        else:
            F.add("MED", f"far {side} {otype} rejected: {str(rr.get('data'))[:100]}")
    time.sleep(4.0)
    data = x.c.fetch_all_followers_positions(x.emails, instance=x.inst)
    with_pos = [e for e, d in data.items() if d.get("count", 0)]
    if with_pos:
        F.add("HIGH", f"{len(with_pos)} followers hold positions although no master order filled")
    for oid in ids:
        x.c.cancel_order(x.master, oid, x.inst)
    time.sleep(4.0)

    def pend(d):
        return len([o for o in d.get("orders", []) if getf(o, "state", "status") in ("PENDING", "OPEN", "NEW")
                    and o.get("type") in ("LIMIT", "STOP")])
    ords = x.c.fetch_all_followers_orders(x.emails, instance=x.inst)
    leftover = {e: pend(d) for e, d in ords.items() if pend(d)}
    F.metrics.update(master_pending_placed=len(ids), followers_with_positions=len(with_pos), followers_with_leftover_pending=len(leftover))
    if leftover:
        F.add("HIGH", f"{len(leftover)} followers keep pending orders after master cancelled all of its own")
    return F.result()


def x8_churn(x: Ctx, rng=None, **_):
    print("\n[X8] Open/close churn")
    F = Findings("X8 Open/close churn")
    reset(x)
    base = {e: funds(x.c, e, x.inst)["balance"] for e in x.of("M1")}
    m0 = funds(x.c, x.master, x.inst)["balance"]
    cycles, fails = 12, 0
    for i in range(cycles):
        side = "BUY" if i % 2 == 0 else "SELL"
        r = buy(x, rng.choice([0.05, 0.1, 0.25, 0.5]), side)
        mid = mkt_id(r)
        if not mid:
            fails += 1; continue
        x.c.squareoff_position(x.master, mid, x.inst)          # immediate close - no wait
    F.metrics.update(cycles=cycles, master_open_failures=fails)
    verify(x, F, "flat after churn", timeout=20)
    time.sleep(1.5)
    stuck = {e: funds(x.c, e, x.inst) for e in x.emails}
    bad_margin = [e for e, f in stuck.items() if abs(f["used_margin"]) > 0.01]
    if bad_margin:
        F.add("HIGH", f"{len(bad_margin)} followers with stuck margin after churn, e.g. {bad_margin[0]} {stuck[bad_margin[0]]['used_margin']}")
    dm = funds(x.c, x.master, x.inst)["balance"] - m0
    d1 = [funds(x.c, e, x.inst)["balance"] - base[e] for e in base]
    if d1:
        F.add("INFO", f"churn PnL master {dm:+.2f} | normal followers avg {sum(d1) / len(d1):+.2f} (min {min(d1):+.2f}, max {max(d1):+.2f})")
        if max(d1) - min(d1) > 25:
            F.add("MED", f"identical 1x followers diverged by {max(d1) - min(d1):.2f} USD over {cycles} cycles")
    return F.result()


def x9_chained(x: Ctx, **_):
    print("\n[X9] Chained concurrent ops")
    F = Findings("X9 Chained concurrent ops")
    for rnd in range(1, 6):
        reset(x)
        r = buy(x, 1.0)
        mid, px = mkt_id(r), float(r["data"]["position"]["avg_entry_price"])

        def op(i):
            if i == 0:
                return x.c.set_position_protection(x.master, mid, tp=round(px * 1.05, 1), sl=round(px * 0.95, 1), instance=x.inst)
            if i == 1:
                return x.c.reduce_position(x.master, mid, 0.3, x.inst)
            if i == 2:
                return buy(x, 0.5)
            return buy(x, 0.2, "SELL")
        res = parallel(op, 4)
        five = [r_ for r_ in res if is_5xx(r_)]
        if five:
            F.add("HIGH", f"round {rnd}: 5xx during chained ops: {five[0]['data']}")
        verify(x, F, f"round {rnd} settled")
    reset(x)
    return F.result()


def x10_random(x: Ctx, rng=None, seed=0, **_):
    print(f"\n[X10] Seeded random walk (seed={seed})")
    F = Findings(f"X10 Seeded random walk (seed {seed})")
    reset(x)
    log = []
    ok = True
    for i in range(1, 26):
        pos = master_positions(x)
        roll = rng.random()
        if roll < 0.55 or not pos:
            side, q = rng.choice(["BUY", "SELL"]), rng.choice([0.1, 0.2, 0.5, 1.0])
            buy(x, q, side); log.append(f"{i}: open {side} {q}")
        elif roll < 0.8:
            p = rng.choice(pos); q = round(pos_qty(p) * rng.choice([0.25, 0.5, 0.75]), 4)
            if q > 0:
                x.c.reduce_position(x.master, p["market_order_id"], q, x.inst); log.append(f"{i}: reduce {p['market_order_id'][-6:]} {q}")
        elif roll < 0.95:
            p = rng.choice(pos); x.c.squareoff_position(x.master, p["market_order_id"], x.inst); log.append(f"{i}: close {p['market_order_id'][-6:]}")
        else:
            p = rng.choice(pos)
            e = float(p.get("avg_entry_price") or 0)
            if e:
                x.c.set_position_protection(x.master, p["market_order_id"], tp=round(e * 1.1, 1), sl=round(e * 0.9, 1), instance=x.inst)
                log.append(f"{i}: protect {p['market_order_id'][-6:]}")
        time.sleep(0.3)
        if i % 5 == 0 and not verify(x, F, f"checkpoint after op {i}"):
            ok = False
            F.add("INFO", f"reproduce with --only X10 --seed {seed}; ops so far: {log[-5:]}")
            break
    x.c.bulk_squareoff(x.master, x.inst)
    verify(x, F, "flat at end")
    F.metrics.update(ops=log, seed=seed)
    return F.result()


SCENARIOS = {"X1": x1_mixed_modes, "X2": x2_reverse, "X3": x3_pyramid, "X4": x4_protection, "X5": x5_intervention,
             "X6": x6_multiplier_change, "X7": x7_phantom, "X8": x8_churn, "X9": x9_chained, "X10": x10_random}


def write_reports(results, args, n) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = BASE_DIR / "reports" / "evidence"
    out.mkdir(parents=True, exist_ok=True)
    jp, mp = out / f"copy_complex_evidence_{ts}.json", out / f"copy_complex_evidence_{ts}.md"
    jp.write_text(json.dumps({"suite": "Complex Copy-Trading Scenarios", "timestamp": datetime.now(timezone.utc).isoformat(),
                              "instance": args.instance, "followers": n, "seed": args.seed, "results": results}, indent=2, default=str), encoding="utf-8")
    icon = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌", "SKIP": "⏭️", "ERROR": "💥"}
    lines = ["# Complex Copy-Trading Scenarios", "", f"**Generated:** {datetime.now(timezone.utc).isoformat()}  ",
             f"**Instance:** `{args.instance}` | **Followers:** {n} | **Seed:** {args.seed}", "",
             "| Scenario | Result | Findings |", "| :--- | :---: | :--- |"]
    for r in results:
        hi = sum(f["severity"] == "HIGH" for f in r["findings"]); md = sum(f["severity"] == "MED" for f in r["findings"])
        lines.append(f"| {r['name']} | {icon.get(r['status'], '?')} {r['status']} | {hi} HIGH, {md} MED |")
    lines += ["", "## Findings", ""]
    for r in results:
        if r["findings"]:
            lines.append(f"### {r['name']}")
            lines += [f"- **{f['severity']}** - {f['message']}" for f in r["findings"]]
            lines.append("")
    mp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return mp


def main() -> int:
    ap = argparse.ArgumentParser(description="Complex copy-trading scenarios")
    ap.add_argument("--master", default=MASTER_EMAIL)
    ap.add_argument("--master-id", default=MASTER_ID)
    ap.add_argument("--prefix", default=DEFAULT_PREFIX)
    ap.add_argument("--domain", default=DEFAULT_DOMAIN)
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int, default=min(20, FOLLOWER_COUNT))
    ap.add_argument("--instance", default="paper")
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--only", default="")
    ap.add_argument("--i-understand-real-money", action="store_true")
    a = ap.parse_args()
    if a.instance != "paper" and not a.i_understand_real_money:
        print("Refusing to run on non-paper instance without --i-understand-real-money"); return 2
    emails = [f"{a.prefix}{i}@{a.domain}" for i in range(a.start, a.end + 1)]
    if len(emails) < 10:
        print("Need at least 10 followers so every cohort has a member"); return 2
    c = BlackTraderClient(base_url=BASE_URL, max_workers=10)
    x = Ctx(c, a.master, a.master_id, emails, a.instance, a.start)
    print("=" * 80 + f"\n COMPLEX COPY-TRADING SCENARIOS | {len(emails)} followers | seed {a.seed}\n" + "=" * 80)
    reset(x)
    setup_cohorts(x)
    rng = random.Random(a.seed)
    wanted = [s.strip().upper() for s in a.only.split(",") if s.strip()] or list(SCENARIOS)
    results: List[Dict[str, Any]] = []
    try:
        for key in wanted:
            fn = SCENARIOS.get(key)
            if not fn:
                continue
            try:
                results.append(fn(x, rng=rng, seed=a.seed))
            except Exception as e:
                print(f"  => {key}: ERROR {type(e).__name__}: {e}")
                results.append({"name": key, "status": "ERROR", "metrics": {}, "findings": [{"severity": "HIGH", "message": f"runner exception: {e}"}]})
            try:
                reset(x)
            except Exception:
                pass
    finally:
        print("[*] Restoring follower settings and balances ...")
        restore(x)
        reset(x)
    mp = write_reports(results, a, len(emails))
    tally = {}
    for r in results:
        tally[r["status"]] = tally.get(r["status"], 0) + 1
    print("\n" + "=" * 80 + f"\n SUMMARY: {tally}\n Report : {mp}\n" + "=" * 80)
    return 1 if any(r["status"] in ("FAIL", "ERROR") for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
