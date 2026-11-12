#!/usr/bin/env python3
"""
BlackTrader Breakpoint & Race-Condition Hunter
==============================================
Goes beyond the happy-path race suites and tries to BREAK the OMS / copy engine.
Every scenario checks an invariant; a violated invariant is a finding.

Scenarios
---------
B1  Duplicate squareoff storm      N concurrent closes of ONE position  -> closed once, credited once
B2  Over-reduce race               concurrent partial closes > position -> qty never negative / flipped
B3  Protection write storm         concurrent TP/SL updates             -> TP and SL come from ONE write (no torn pair)
B4  Double-cancel storm            N concurrent cancels of one order    -> no 5xx, order gone
B5  Load ramp (breaking point)     10/25/50/100 concurrent master orders-> find where fan-out drops, duplicates, errors
B6  Follow/unfollow flapping       link-state hammering during trades   -> no duplicate links => no double fan-out
B7  Margin exhaustion              low-balance follower + order burst   -> used_margin never exceeds equity
B8  Input fuzz under concurrency   invalid / hostile payloads           -> 4xx only, never 5xx, never a position
B9  Bulk vs individual close       bulk + single squareoffs together    -> 0 positions, 0 margin, no 5xx
B10 Auth/token refresh storm       parallel forced re-logins            -> all sessions valid afterwards
B11 Final consistency audit        all accounts after teardown          -> 0 positions, 0 pending, margin 0, equity==balance

Severity:  HIGH = invariant broken (system bug)   MED = suspicious / non-idempotent   INFO = measurement

Safety: runs on the PAPER instance only unless --i-understand-real-money is passed.

Usage:
    python test_suite/breakpoint_race_runner.py --end 20
    python test_suite/breakpoint_race_runner.py --only B1,B2,B5 --ramp 10,25,50
"""

import argparse
import json
import math
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config.settings import BASE_URL, DEFAULT_PREFIX, DEFAULT_DOMAIN, MASTER_EMAIL, MASTER_ID, FOLLOWER_COUNT
from test_suite.baseline import get_expected_multiplier
from test_suite.client import BlackTraderClient

SYMBOL = "BINANCE:BTCUSDT.P"


# --------------------------------------------------------------------------- helpers
class Findings:
    def __init__(self, name: str):
        self.name = name
        self.items: List[Dict[str, str]] = []
        self.metrics: Dict[str, Any] = {}

    def add(self, sev: str, msg: str):
        self.items.append({"severity": sev, "message": msg})
        print(f"    [{sev}] {msg}")

    def result(self, status: Optional[str] = None) -> Dict[str, Any]:
        if status is None:
            sevs = {i["severity"] for i in self.items}
            status = "FAIL" if "HIGH" in sevs else ("WARN" if "MED" in sevs else "PASS")
        print(f"  => {self.name}: {status}")
        return {"name": self.name, "status": status, "findings": self.items, "metrics": self.metrics}


def mkt_id(res: dict) -> Optional[str]:
    d = res.get("data")
    return d.get("order", {}).get("market_order_id") if isinstance(d, dict) else None


def ord_id(res: dict) -> Optional[str]:
    d = res.get("data")
    return d.get("order", {}).get("order_id") if isinstance(d, dict) else None


def is_5xx(res: dict) -> bool:
    return int(res.get("status_code", 0)) >= 500


def getf(d: dict, *keys, default=None):
    for k in keys:
        if d.get(k) is not None:
            return d[k]
    return default


def pos_qty(p: dict) -> float:
    return float(getf(p, "net_qty", "qty", "quantity", default=0.0) or 0.0)


def funds(client, email, instance) -> Dict[str, float]:
    f = client.get_positions(email, instance).get("funds", {}) or {}
    return {k: float(f.get(k, 0.0) or 0.0) for k in ("balance", "equity", "used_margin")}


def reset(client, master, emails, instance):
    client.teardown_all_accounts(master, emails, instance=instance)
    time.sleep(1.5)


def wait_fanout(client, emails, expected: int, instance, timeout=20.0):
    """Poll until every follower holds >= expected positions. Returns (lag_sec, counts)."""
    t0 = time.time()
    counts: Dict[str, int] = {}
    while time.time() - t0 < timeout:
        data = client.fetch_all_followers_positions(emails, instance=instance)
        counts = {e: d.get("count", 0) for e, d in data.items()}
        if all(c >= expected for c in counts.values()):
            return time.time() - t0, counts
        time.sleep(0.5)
    return time.time() - t0, counts


def first_position(client, email, instance) -> Optional[dict]:
    ps = client.get_positions(email, instance).get("positions", [])
    return ps[0] if ps else None


def parallel(fn, n: int, workers: Optional[int] = None):
    """Release n calls of fn(i) at the same instant (barrier) and return results."""
    barrier = threading.Barrier(n)

    def run(i):
        try:
            barrier.wait(timeout=30)
        except threading.BrokenBarrierError:
            pass
        t = time.perf_counter()
        try:
            r = fn(i)
        except Exception as e:  # network error is itself a finding
            r = {"status_code": 599, "data": f"EXC {type(e).__name__}: {e}"}
        if isinstance(r, dict):
            r["_latency"] = time.perf_counter() - t
        return r

    with ThreadPoolExecutor(max_workers=workers or n) as ex:
        return list(ex.map(run, range(n)))


# --------------------------------------------------------------------------- scenarios
def b1_dup_squareoff(c, master, emails, inst, **_):
    print("\n[B1] Duplicate squareoff storm (double-close / double-credit)")
    F = Findings("B1 Duplicate squareoff storm")
    reset(c, master, emails, inst)
    m = mkt_id(c.place_order(master, qty=1.0, instance=inst))
    wait_fanout(c, emails, 1, inst)
    f = emails[0]
    pos = first_position(c, f, inst)
    if not pos:
        F.add("HIGH", "follower did not receive copied position - cannot run scenario")
        return F.result()
    bal0 = funds(c, f, inst)["balance"]
    n = 20
    res = parallel(lambda i: c.squareoff_position(f, pos["market_order_id"], inst), n)
    ok = [r for r in res if r["status_code"] == 200]
    fivexx = [r for r in res if is_5xx(r)]
    time.sleep(1.5)
    bal1 = funds(c, f, inst)["balance"]
    pnls = [float(r["data"].get("realized_pnl", 0.0)) for r in ok if isinstance(r["data"], dict)]
    one_pnl = pnls[0] if pnls else 0.0
    delta = bal1 - bal0
    F.metrics.update(concurrent_closes=n, http_200=len(ok), http_5xx=len(fivexx), balance_delta=round(delta, 6),
                     single_realized_pnl=round(one_pnl, 6), distinct_pnl_values=len(set(pnls)))
    if fivexx:
        F.add("HIGH", f"{len(fivexx)}/{n} concurrent closes returned 5xx: {fivexx[0]['data']}")
    if len(ok) > 1:
        F.add("MED", f"{len(ok)}/{n} closes of the same position returned 200 (non-idempotent responses)")
    if abs(delta - one_pnl) > max(0.05, abs(one_pnl) * 0.01):
        F.add("HIGH", f"DOUBLE CREDIT/DEBIT: balance moved {delta:+.4f} but a single close realises {one_pnl:+.4f}")
    if first_position(c, f, inst):
        F.add("HIGH", "position still open after close storm")
    c.squareoff_position(master, m, inst) if m else None
    return F.result()


def b2_over_reduce(c, master, emails, inst, **_):
    print("\n[B2] Over-reduce race (qty underflow / side flip)")
    F = Findings("B2 Over-reduce race")
    reset(c, master, emails, inst)
    c.place_order(master, qty=1.0, instance=inst)
    wait_fanout(c, emails, 1, inst)
    f = emails[0]
    pos = first_position(c, f, inst)
    if not pos:
        F.add("HIGH", "no follower position")
        return F.result()
    q0, side0 = pos_qty(pos), pos.get("side")
    chunk = round(q0 * 0.4, 8)
    n = 5
    res = parallel(lambda i: c.reduce_position(f, pos["market_order_id"], chunk, inst), n)
    ok = sum(1 for r in res if r["status_code"] == 200)
    fivexx = [r for r in res if is_5xx(r)]
    time.sleep(1.5)
    after = c.get_positions(f, inst).get("positions", [])
    final = sum(pos_qty(p) for p in after if p.get("market_order_id") == pos["market_order_id"])
    expected = max(0.0, q0 - chunk * ok)
    F.metrics.update(start_qty=q0, reduce_chunk=chunk, attempts=n, accepted=ok, final_qty=final, expected_qty=expected)
    if fivexx:
        F.add("HIGH", f"{len(fivexx)} reduce calls returned 5xx: {fivexx[0]['data']}")
    if final < -1e-9:
        F.add("HIGH", f"NEGATIVE position qty {final}")
    if abs(final - expected) > max(1e-6, q0 * 1e-4):
        F.add("HIGH", f"qty accounting drift: accepted {ok} reduces of {chunk}, expected {expected}, got {final}")
    if any(p.get("side") != side0 for p in after if p.get("market_order_id") == pos["market_order_id"]):
        F.add("HIGH", "position side flipped")
    if ok * chunk > q0 + 1e-9:
        F.add("MED", f"server accepted {ok * chunk:.6f} total reduce on a {q0} position (clamped?)")
    reset(c, master, emails, inst)
    return F.result()


def b3_protection_storm(c, master, emails, inst, **_):
    print("\n[B3] Protection write storm (torn TP/SL pair)")
    F = Findings("B3 Protection write storm")
    reset(c, master, emails, inst)
    c.place_order(master, qty=0.1, instance=inst)
    wait_fanout(c, emails, 1, inst)
    f = emails[0]
    pos = first_position(c, f, inst)
    if not pos:
        F.add("HIGH", "no follower position")
        return F.result()
    entry = float(getf(pos, "avg_entry_price", "entry_price", default=0) or 0)
    if entry <= 0:
        F.add("MED", "could not read entry price; skipping")
        return F.result("SKIP")
    n = 20
    tps = [round(entry * (1 + 0.01 * (i + 1)), 2) for i in range(n)]
    sls = [round(entry * (1 - 0.01 * (i + 1)), 2) for i in range(n)]
    side_buy = pos.get("side") == "BUY"
    res = parallel(lambda i: c.set_position_protection(
        f, pos["market_order_id"], tp=tps[i] if side_buy else sls[i], sl=sls[i] if side_buy else tps[i], instance=inst), n)
    fivexx = [r for r in res if is_5xx(r)]
    time.sleep(1.0)
    p = next((x for x in c.get_positions(f, inst).get("positions", []) if x.get("market_order_id") == pos["market_order_id"]), {})
    tp = (p.get("tp_order") or {}).get("trigger_price")
    sl = (p.get("sl_order") or {}).get("trigger_price")
    F.metrics.update(writes=n, http_5xx=len(fivexx), final_tp=tp, final_sl=sl)
    if fivexx:
        F.add("HIGH", f"{len(fivexx)}/{n} protection updates returned 5xx: {fivexx[0]['data']}")
    if tp is None or sl is None:
        F.add("HIGH", f"protection lost after storm (tp={tp}, sl={sl})")
    else:
        hi, lo = (tp, sl) if side_buy else (sl, tp)
        try:
            i_hi, i_lo = tps.index(round(float(hi), 2)), sls.index(round(float(lo), 2))
            if i_hi != i_lo:
                F.add("HIGH", f"TORN WRITE: TP from request #{i_hi} but SL from request #{i_lo}")
        except ValueError:
            F.add("HIGH", f"final TP/SL ({tp}/{sl}) match none of the submitted values")
    reset(c, master, emails, inst)
    return F.result()


def b4_double_cancel(c, master, emails, inst, **_):
    print("\n[B4] Double-cancel storm")
    F = Findings("B4 Double-cancel storm")
    f = emails[0]
    c.bulk_cancel(f, inst)
    px = None
    pos_m = c.place_order(f, qty=0.01, instance=inst)  # market, to read a price
    mid = mkt_id(pos_m)
    p = first_position(c, f, inst)
    if p:
        px = float(getf(p, "avg_entry_price", "entry_price", default=0) or 0)
    if mid:
        c.squareoff_position(f, mid, inst)
    if not px:
        F.add("MED", "no market price available; skipping")
        return F.result("SKIP")
    o = ord_id(c.place_order(f, side="BUY", order_type="LIMIT", qty=0.01, price=round(px * 0.5, 2), instance=inst))
    if not o:
        F.add("HIGH", "could not place far-from-market LIMIT order")
        return F.result()
    n = 20
    res = parallel(lambda i: c.cancel_order(f, o, inst), n)
    ok = sum(1 for r in res if r["status_code"] == 200)
    fivexx = [r for r in res if is_5xx(r)]
    time.sleep(1.0)
    still = [x for x in c.get_orders(f, inst).get("orders", []) if x.get("order_id") == o and getf(x, "state", "status") in ("PENDING", "OPEN", "NEW")]
    F.metrics.update(cancels=n, http_200=ok, http_5xx=len(fivexx))
    if fivexx:
        F.add("HIGH", f"{len(fivexx)} cancel calls returned 5xx: {fivexx[0]['data']}")
    if ok == 0:
        F.add("HIGH", "no cancel succeeded")
    if ok > 1:
        F.add("MED", f"{ok} cancels of one order all returned 200")
    if still:
        F.add("HIGH", "order still pending after cancel storm")
    c.bulk_cancel(f, inst)
    return F.result()


def b5_load_ramp(c, master, emails, inst, ramp=(10, 25, 50, 100), **_):
    print(f"\n[B5] Load ramp to breaking point {list(ramp)} x {len(emails)} followers")
    F = Findings("B5 Load ramp (breaking point)")
    levels = []
    broke_at = None
    for n in ramp:
        reset(c, master, emails, inst)
        t0 = time.time()
        res = parallel(lambda i: c.place_order(master, qty=0.01, side="BUY", instance=inst), n)
        burst = time.time() - t0
        ids = [mkt_id(r) for r in res if mkt_id(r)]
        lat = sorted(r["_latency"] for r in res)
        codes: Dict[int, int] = {}
        for r in res:
            codes[r["status_code"]] = codes.get(r["status_code"], 0) + 1
        lag, counts = wait_fanout(c, emails, len(ids), inst, timeout=25)
        short = sum(1 for v in counts.values() if v < len(ids))
        dup = sum(1 for v in counts.values() if v > len(ids))
        lvl = {"threads": n, "placed": len(ids), "status_codes": codes,
               "p50_s": round(statistics.median(lat), 3), "p95_s": round(lat[int(len(lat) * 0.95) - 1], 3),
               "max_s": round(lat[-1], 3), "burst_s": round(burst, 3), "fanout_lag_s": round(lag, 2),
               "followers_short": short, "followers_duplicated": dup,
               "positions_expected": len(ids) * len(emails), "positions_actual": sum(counts.values())}
        levels.append(lvl)
        print(f"    n={n:>3} placed={len(ids)} codes={codes} p95={lvl['p95_s']}s lag={lvl['fanout_lag_s']}s short={short} dup={dup}")
        if dup:
            F.add("HIGH", f"@{n} concurrent: {dup} followers received DUPLICATE copies")
        if short:
            F.add("HIGH", f"@{n} concurrent: {short} followers MISSING copies "
                          f"({lvl['positions_actual']}/{lvl['positions_expected']} positions) after {lag:.0f}s")
        bad = {k: v for k, v in codes.items() if k != 200}
        if bad:
            F.add("MED", f"@{n} concurrent: non-200 responses {bad}")
        if (short or dup or bad) and broke_at is None:
            broke_at = n
            if short or dup:
                break  # stop escalating once correctness breaks
    F.metrics.update(levels=levels, first_degradation_at_threads=broke_at)
    F.add("INFO", f"first degradation at: {broke_at if broke_at else 'not reached'} concurrent master orders")
    reset(c, master, emails, inst)
    return F.result()


def b6_flapping(c, master, emails, inst, master_id="", **_):
    print("\n[B6] Follow/unfollow flapping (duplicate-link detection)")
    F = Findings("B6 Follow/unfollow flapping")
    from test_suite.client import paper_unfollow_blocked, PAPER_UNFOLLOW_REASON
    if paper_unfollow_blocked(inst):
        F.add("INFO", "skipped: " + PAPER_UNFOLLOW_REASON)
        return F.result("SKIP")
    reset(c, master, emails, inst)
    probe = emails[-1]

    def flap(i):
        for k in range(10):
            if (i + k) % 2 == 0:
                c.unfollow_master(probe, master_id, inst)
            else:
                c.follow_master(probe, master_id, inst, multiplier=1.0)
        return {"status_code": 200}

    def trades(_i):
        for _ in range(5):
            c.place_order(master, qty=0.01, instance=inst)
            time.sleep(0.1)
        return {"status_code": 200}

    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(flap, i) for i in range(6)] + [ex.submit(trades, 0)]
        for f_ in futs:
            f_.result()
    time.sleep(2.0)
    links = [x for x in c.get_copy_followers(master, inst, active_only=False)
             if probe in json.dumps(x)]
    F.metrics["probe_link_rows"] = len(links)
    if len(links) > 1:
        F.add("HIGH", f"{len(links)} link rows exist for ONE follower after flapping")
    reset(c, master, emails, inst)
    c.unfollow_master(probe, master_id, inst)
    c.follow_master(probe, master_id, inst, multiplier=1.0)
    time.sleep(1.0)
    c.place_order(master, qty=0.01, instance=inst)
    wait_fanout(c, emails, 1, inst, timeout=10)
    cnt = c.get_positions(probe, inst).get("count", 0)
    F.metrics["probe_positions_after_single_master_order"] = cnt
    if cnt > 1:
        F.add("HIGH", f"DOUBLE FAN-OUT: probe got {cnt} positions for 1 master order (duplicate subscription)")
    elif cnt == 0:
        F.add("HIGH", "probe got NO position after clean re-follow (state machine stuck)")
    reset(c, master, emails, inst)
    return F.result()


def b7_margin_exhaustion(c, master, emails, inst, **_):
    print("\n[B7] Margin exhaustion (over-leverage)")
    F = Findings("B7 Margin exhaustion")
    reset(c, master, emails, inst)
    probe = emails[1]
    member = next((m for m in c.get_admin_members() if m.get("email") == probe), None)
    mid_ = member and getf(member, "client_id", "id", "member_id")
    if not mid_:
        F.add("MED", "member id not found via admin API; skipping")
        return F.result("SKIP")
    orig = funds(c, probe, inst)["balance"]
    try:
        c.set_member_balance(mid_, 1000.0, inst)
        time.sleep(0.5)
        res = parallel(lambda i: c.place_order(master, qty=1.0, instance=inst), 20)
        placed = sum(1 for r in res if mkt_id(r))
        time.sleep(6.0)
        fd = funds(c, probe, inst)
        cnt = c.get_positions(probe, inst).get("count", 0)
        F.metrics.update(master_orders=placed, follower_positions=cnt, **{f"follower_{k}": v for k, v in fd.items()})
        if fd["used_margin"] > fd["equity"] + 1.0:
            F.add("HIGH", f"OVER-LEVERAGED: used_margin {fd['used_margin']:.2f} > equity {fd['equity']:.2f} "
                          f"with {cnt}/{placed} copied positions")
        if cnt >= placed > 0:
            F.add("MED", "$1,000 follower copied every large order - margin check may be missing")
        if fd["balance"] < 0:
            F.add("HIGH", f"NEGATIVE balance {fd['balance']}")
    finally:
        reset(c, master, emails, inst)
        c.set_member_balance(mid_, orig, inst)
    return F.result()


def b8_fuzz(c, master, emails, inst, **_):
    print("\n[B8] Hostile input fuzz under concurrency")
    F = Findings("B8 Input fuzz")
    f = emails[2]
    c.bulk_squareoff(f, inst)
    token = c.get_trader_token(f)
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "X-Broker-ID": inst}
    url = f"{c.base_url}/v1/oms/{inst}/orders"
    bad = [
        {"symbol": SYMBOL, "side": "BUY", "type": "MARKET", "qty": 0},
        {"symbol": SYMBOL, "side": "BUY", "type": "MARKET", "qty": -1},
        {"symbol": SYMBOL, "side": "BUY", "type": "MARKET", "qty": "abc"},
        {"symbol": SYMBOL, "side": "BUY", "type": "MARKET", "qty": None},
        {"symbol": SYMBOL, "side": "BUY", "type": "MARKET", "qty": float("nan")},
        {"symbol": SYMBOL, "side": "BUY", "type": "MARKET", "qty": float("inf")},
        {"symbol": SYMBOL, "side": "BUY", "type": "MARKET", "qty": 1e18},
        {"symbol": SYMBOL, "side": "BUY", "type": "MARKET", "qty": [1]},
        {"symbol": SYMBOL, "side": "BUY", "type": "MARKET"},
        {"symbol": "NOPE:FAKE", "side": "BUY", "type": "MARKET", "qty": 1},
        {"symbol": "", "side": "BUY", "type": "MARKET", "qty": 1},
        {"symbol": SYMBOL, "side": "HOLD", "type": "MARKET", "qty": 1},
        {"symbol": SYMBOL, "side": "BUY", "type": "WEIRD", "qty": 1},
        {"symbol": SYMBOL, "side": "BUY", "type": "LIMIT", "qty": 1},                  # limit w/o price
        {"symbol": SYMBOL, "side": "BUY", "type": "LIMIT", "qty": 1, "price": -5},
        {"symbol": "A" * 10000, "side": "BUY", "type": "MARKET", "qty": 1},
        {"symbol": "'; DROP TABLE orders;--", "side": "BUY", "type": "MARKET", "qty": 1},
        {"symbol": SYMBOL, "side": "BUY", "type": "MARKET", "qty": 0.01, "tp": -1, "sl": 1e30},
    ]
    reps = 5
    jobs = [p for p in bad for _ in range(reps)]

    def hit(i):
        try:
            r = c.session.post(url, headers=h, data=json.dumps(jobs[i]), timeout=c.timeout)
            return {"status_code": r.status_code, "payload": jobs[i], "data": r.text[:200]}
        except Exception as e:
            return {"status_code": 599, "payload": jobs[i], "data": f"EXC {type(e).__name__}: {e}"}

    res = parallel(hit, len(jobs), workers=20)
    five = [r for r in res if is_5xx(r)]
    accepted = [r for r in res if r["status_code"] == 200]
    time.sleep(1.0)
    leftover = c.get_positions(f, inst).get("count", 0)
    F.metrics.update(requests=len(jobs), http_5xx=len(five), http_200=len(accepted), positions_created=leftover)
    seen = set()
    for r in five:
        k = json.dumps(r["payload"], sort_keys=True, default=str)[:120]
        if k not in seen:
            seen.add(k)
            F.add("HIGH", f"5xx on invalid input {k} -> {r['status_code']} {r['data'][:80]}")
    seen = set()
    for r in accepted:
        k = json.dumps(r["payload"], sort_keys=True, default=str)[:120]
        if k not in seen:
            seen.add(k)
            F.add("HIGH", f"INVALID input ACCEPTED (200): {k}")
    c.bulk_squareoff(f, inst)
    c.bulk_cancel(f, inst)
    return F.result()


def b9_bulk_vs_single(c, master, emails, inst, **_):
    print("\n[B9] Bulk squareoff racing individual squareoffs")
    F = Findings("B9 Bulk vs individual close")
    f = emails[3]
    c.bulk_squareoff(f, inst)
    ids = [mkt_id(c.place_order(f, qty=0.01, instance=inst)) for _ in range(6)]
    ids = [i for i in ids if i]
    time.sleep(1.0)

    def act(i):
        if i < len(ids):
            return c.squareoff_position(f, ids[i], inst)
        return c.bulk_squareoff(f, inst)

    res = parallel(act, len(ids) + 2)
    five = [r for r in res if is_5xx(r)]
    time.sleep(1.5)
    left = c.get_positions(f, inst).get("count", 0)
    fd = funds(c, f, inst)
    F.metrics.update(positions_opened=len(ids), http_5xx=len(five), positions_left=left, **{f"final_{k}": v for k, v in fd.items()})
    if five:
        F.add("HIGH", f"{len(five)} 5xx during close race: {five[0]['data']}")
    if left:
        F.add("HIGH", f"{left} positions left open after bulk+single close race")
    if abs(fd["used_margin"]) > 0.01:
        F.add("HIGH", f"STUCK MARGIN {fd['used_margin']} with no open positions")
    return F.result()


def b10_auth_storm(c, master, emails, inst, **_):
    print("\n[B10] Token refresh storm")
    F = Findings("B10 Auth/token refresh storm")
    f = emails[4]
    n = 30
    res = parallel(lambda i: {"status_code": 200 if c.get_trader_token(f, force_refresh=True) else 401}, n)
    bad = [r for r in res if r["status_code"] != 200]
    after = parallel(lambda i: {"status_code": 200 if "error" not in c.get_positions(f, inst) else 500}, n)
    bad2 = [r for r in after if r["status_code"] != 200]
    F.metrics.update(logins=n, login_failures=len(bad), post_storm_read_failures=len(bad2))
    if bad:
        F.add("HIGH", f"{len(bad)}/{n} parallel logins failed")
    if bad2:
        F.add("HIGH", f"{len(bad2)}/{n} authenticated reads failed after login storm (token invalidation race)")
    return F.result()


def b11_audit(c, master, emails, inst, **_):
    print("\n[B11] Final consistency audit")
    F = Findings("B11 Final consistency audit")
    reset(c, master, emails, inst)
    time.sleep(2.0)
    allm = [master] + emails
    pos = c.fetch_all_followers_positions(allm, instance=inst)
    ords = c.fetch_all_followers_orders(allm, instance=inst)
    orphans = {e: d.get("count", 0) for e, d in pos.items() if d.get("count", 0)}
    pend = {e: len([o for o in d.get("orders", []) if getf(o, "state", "status") in ("PENDING", "OPEN", "NEW")]) for e, d in ords.items()}
    pend = {e: n for e, n in pend.items() if n}
    margin = {e: d.get("funds", {}).get("used_margin") for e, d in pos.items()
              if abs(float(d.get("funds", {}).get("used_margin", 0) or 0)) > 0.01}
    eqdrift = {e: (d["funds"].get("equity"), d["funds"].get("balance")) for e, d in pos.items()
               if d.get("funds") and abs(float(d["funds"].get("equity", 0) or 0) - float(d["funds"].get("balance", 0) or 0)) > 0.01}
    F.metrics.update(accounts=len(allm), orphan_positions=len(orphans), pending_orders=len(pend),
                     stuck_margin=len(margin), equity_balance_drift=len(eqdrift))
    if orphans:
        F.add("HIGH", f"{len(orphans)} accounts with orphan positions: {dict(list(orphans.items())[:5])}")
    if pend:
        F.add("HIGH", f"{len(pend)} accounts with leftover pending orders")
    if margin:
        F.add("HIGH", f"{len(margin)} accounts with stuck margin: {dict(list(margin.items())[:5])}")
    if eqdrift:
        F.add("HIGH", f"{len(eqdrift)} accounts where equity != balance while flat: {dict(list(eqdrift.items())[:5])}")
    return F.result()


SCENARIOS = {
    "B1": b1_dup_squareoff, "B2": b2_over_reduce, "B3": b3_protection_storm, "B4": b4_double_cancel,
    "B5": b5_load_ramp, "B6": b6_flapping, "B7": b7_margin_exhaustion, "B8": b8_fuzz,
    "B9": b9_bulk_vs_single, "B10": b10_auth_storm, "B11": b11_audit,
}


# --------------------------------------------------------------------------- main
def write_reports(results, args, emails) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = BASE_DIR / "reports" / "evidence"
    out.mkdir(parents=True, exist_ok=True)
    jp, mp = out / f"breakpoint_race_evidence_{ts}.json", out / f"breakpoint_race_evidence_{ts}.md"
    jp.write_text(json.dumps({"suite": "Breakpoint & Race Hunter", "timestamp": datetime.now(timezone.utc).isoformat(),
                              "instance": args.instance, "followers": len(emails), "results": results}, indent=2, default=str),
                  encoding="utf-8")
    icon = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌", "SKIP": "⏭️", "ERROR": "💥"}
    lines = [f"# Breakpoint & Race-Condition Hunter Report", "",
             f"**Generated:** {datetime.now(timezone.utc).isoformat()}  ",
             f"**Instance:** `{args.instance}` | **Followers:** {len(emails)} | **Master:** `{args.master}`", "",
             "| Scenario | Result | Findings |", "| :--- | :---: | :--- |"]
    for r in results:
        hi = sum(1 for f in r.get("findings", []) if f["severity"] == "HIGH")
        md = sum(1 for f in r.get("findings", []) if f["severity"] == "MED")
        lines.append(f"| {r['name']} | {icon.get(r['status'], '?')} {r['status']} | {hi} HIGH, {md} MED |")
    lines += ["", "## Findings", ""]
    for r in results:
        if r.get("findings"):
            lines.append(f"### {r['name']}")
            lines += [f"- **{f['severity']}** — {f['message']}" for f in r["findings"]]
            lines.append("")
    ramp = next((r for r in results if r["name"].startswith("B5")), None)
    if ramp and ramp.get("metrics", {}).get("levels"):
        lines += ["## Load ramp", "", "| Threads | Placed | p50 s | p95 s | Fan-out lag s | Short | Dup | Positions |",
                  "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: |"]
        for l in ramp["metrics"]["levels"]:
            lines.append(f"| {l['threads']} | {l['placed']} | {l['p50_s']} | {l['p95_s']} | {l['fanout_lag_s']} | "
                         f"{l['followers_short']} | {l['followers_duplicated']} | {l['positions_actual']}/{l['positions_expected']} |")
    mp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return mp


def main() -> int:
    ap = argparse.ArgumentParser(description="BlackTrader breakpoint & race-condition hunter")
    ap.add_argument("--master", default=MASTER_EMAIL)
    ap.add_argument("--master-id", default=MASTER_ID)
    ap.add_argument("--prefix", default=DEFAULT_PREFIX)
    ap.add_argument("--domain", default=DEFAULT_DOMAIN)
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int, default=min(20, FOLLOWER_COUNT), help="Last follower index (default 20; use FOLLOWER_COUNT for full fan-out)")
    ap.add_argument("--instance", default="paper")
    ap.add_argument("--only", default="", help="Comma list, e.g. B1,B5")
    ap.add_argument("--ramp", default="10,25,50,100", help="Concurrency levels for B5")
    ap.add_argument("--i-understand-real-money", action="store_true")
    args = ap.parse_args()

    if args.instance != "paper" and not args.i_understand_real_money:
        print("Refusing to run on non-paper instance without --i-understand-real-money")
        return 2

    emails = [f"{args.prefix}{i}@{args.domain}" for i in range(args.start, args.end + 1)]
    if len(emails) < 6:
        print("Need at least 6 followers (several scenarios use dedicated probe accounts)")
        return 2
    ramp = tuple(int(x) for x in args.ramp.split(","))
    c = BlackTraderClient(base_url=BASE_URL, max_workers=max(10, max(ramp)))
    wanted = [s.strip().upper() for s in args.only.split(",") if s.strip()] or list(SCENARIOS)

    print("=" * 80)
    print(f" BREAKPOINT & RACE HUNTER  |  {len(emails)} followers  |  instance={args.instance}")
    print("=" * 80)
    print("[*] Ensuring followers are linked at 1.0x ...")
    with ThreadPoolExecutor(max_workers=10) as ex:
        list(ex.map(lambda e: c.follow_master(e, args.master_id, args.instance, multiplier=1.0), emails))

    results = []
    try:
        results = _run_scenarios(c, args, emails, ramp, wanted)
    finally:
        print("[*] Restoring baseline multipliers (1x/2x/3x/0.5x cohorts) ...")
        with ThreadPoolExecutor(max_workers=10) as ex:
            list(ex.map(lambda ie: c.follow_master(ie[1], args.master_id, args.instance, method="multiplier",
                                                   multiplier=get_expected_multiplier(args.start + ie[0]), reverse=False),
                        enumerate(emails)))
        try:
            reset(c, args.master, emails, args.instance)
        except Exception:
            pass

    report = write_reports(results, args, emails)
    tally = {}
    for r in results:
        tally[r["status"]] = tally.get(r["status"], 0) + 1
    print()
    print("=" * 80)
    print(f" SUMMARY: {tally}")
    print(f" Report : {report}")
    print("=" * 80)
    return 1 if any(r["status"] in ("FAIL", "ERROR") for r in results) else 0


def _run_scenarios(c, args, emails, ramp, wanted):
    results = []
    for key in wanted:
        fn = SCENARIOS.get(key)
        if not fn:
            continue
        try:
            results.append(fn(c, args.master, emails, args.instance, master_id=args.master_id, ramp=ramp))
        except Exception as e:
            print(f"  => {key}: ERROR {type(e).__name__}: {e}")
            results.append({"name": key, "status": "ERROR", "findings": [{"severity": "HIGH", "message": f"runner exception: {e}"}], "metrics": {}})
        try:
            reset(c, args.master, emails, args.instance)
        except Exception:
            pass

    return results


if __name__ == "__main__":
    sys.exit(main())
