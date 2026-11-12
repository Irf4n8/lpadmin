#!/usr/bin/env python3
"""
End-to-End Copy-Trading Test
============================
One run that walks the whole life of a copied trade, in the order a tester would check it by hand,
and asserts the result on the master AND on every linked follower after each step.

    E01 Preflight            platform reachable, admin + master + every follower can log in
    E02 Copy topology        which followers are linked to the master, with what method / multiplier
    E03 Clean slate          teardown, then prove 0 positions and 0 pending orders everywhere
    E04 Baseline             balances, equity, margin and trade-history watermark per account
    E05 Open & fan-out       master market BUY -> every follower opens master_qty x factor; copy orders reference the master
    E06 Set TP/SL            protection set on the master reaches every follower unchanged
    E07 Modify TP/SL         protection changed on the master is re-synced to every follower
    E08 Partial close        master reduces -> followers reduce proportionally
    E09 Pyramid + hedge      master adds a BUY and opens a SELL hedge leg -> followers mirror both
    E10 Close one position   master closes the hedge leg only -> followers close only that leg
    E11 Close all            master flat -> followers flat, no margin left in use
    E12 Pending orders       far LIMIT / STOP orders never create positions; cancelling leaves nothing pending
    E13 Every market type    one symbol of every market group the platform lists (crypto perp/spot, forex, metals,
                             commodities, CFDs, US/EU stocks, indices, NSE/BSE stocks/futures/options, ...):
                             open -> copied at the right size -> closed everywhere -> PnL matches the contract spec.
                             Closed markets are reported, not failed. Every symbol: test_suite/symbol_coverage_runner.py
    E14 Input validation     invalid orders are rejected with 4xx and never open a position
    E15 Accounting           every closed trade's realized PnL = (exit-entry) x qty x contract size; balance moved by exactly that PnL
    E16 Final audit          0 positions, 0 pending, 0 margin, equity == balance on every account

Expected follower size:  net_qty(follower) = net_qty(master) x factor
    factor = multiplier (multiplier method) | balance ratio x multiplier | equity ratio x multiplier, negative when reverse.

Verdicts per step:  PASS | WARN (suspicious, worth a look) | FAIL (invariant broken = bug) | SKIP (a prerequisite failed)
Paper instance by default; the real instance needs --i-understand-real-money (the dashboard asks you to type REAL).

Usage:
    python test_suite/e2e_runner.py --end 10                 # quick: followers 1-10
    python test_suite/e2e_runner.py                          # all configured followers
    python test_suite/e2e_runner.py --only E05,E06,E11       # just some steps (E01-E04 and E16 always run)
"""

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config.settings import BASE_URL, DEFAULT_PREFIX, DEFAULT_DOMAIN, MASTER_EMAIL, MASTER_ID, FOLLOWER_COUNT
from test_suite.breakpoint_race_runner import Findings, getf, mkt_id, ord_id, pos_qty
from test_suite.client import BlackTraderClient
from test_suite import symbol_coverage_runner as SC

SYM = "BINANCE:BTCUSDT.P"
PENDING_STATES = ("PENDING", "OPEN", "NEW", "WORKING", "ACCEPTED")
SYNC_TIMEOUT = 25.0          # seconds a follower may take to mirror a master action


class SkipStep(Exception):
    """A prerequisite of this step is missing (an earlier step failed)."""


# --------------------------------------------------------------------------------------------- context
class Ctx:
    def __init__(self, c: BlackTraderClient, args, emails: List[str]):
        self.c, self.a, self.inst = c, args, args.instance
        self.master, self.master_id = args.master, args.master_id
        self.emails = emails                      # followers in the requested range
        self.linked: List[str] = []               # followers with an active copy link (the ones we assert on)
        self.factor: Dict[str, float] = {}
        self.link: Dict[str, Dict[str, Any]] = {}
        self.base_funds: Dict[str, Dict[str, float]] = {}
        self.hist_mark: Dict[str, int] = {}
        self.pos_a: Optional[str] = None          # master position A (opened in E05)
        self.pos_hedge: Optional[str] = None      # master SELL hedge leg (E09)
        self.entry_px: Optional[float] = None
        self.lags: List[float] = []
        self.logins_ok = False

    @property
    def everyone(self) -> List[str]:
        return [self.master] + self.emails

    # ---- reads ----
    def positions(self, email: str) -> List[dict]:
        return self.c.get_positions(email, self.inst).get("positions", []) or []

    def all_positions(self, emails: List[str]) -> Dict[str, List[dict]]:
        data = self.c.fetch_all_followers_positions(emails, instance=self.inst)
        return {e: (data.get(e) or {}).get("positions", []) or [] for e in emails}

    def all_funds(self, emails: List[str]) -> Dict[str, Dict[str, float]]:
        data = self.c.fetch_all_followers_positions(emails, instance=self.inst)
        out = {}
        for e in emails:
            f = (data.get(e) or {}).get("funds", {}) or {}
            out[e] = {k: float(f.get(k) or 0.0) for k in ("balance", "equity", "used_margin")}
        return out

    def pending(self, email: str) -> List[dict]:
        return [o for o in self.c.get_orders(email, self.inst).get("orders", [])
                if str(getf(o, "state", "status", default="")).upper() in PENDING_STATES and o.get("type") in ("LIMIT", "STOP")]

    def all_pending(self, emails: List[str]) -> Dict[str, List[dict]]:
        # each call downloads the account's full order history (the API has no filter), so read wider in parallel
        with ThreadPoolExecutor(max_workers=16) as ex:
            return dict(zip(emails, ex.map(self.pending, emails)))

    def master_order(self, side: str, qty: float, **kw) -> Dict[str, Any]:
        return self.c.place_order(self.master, symbol=SYM, side=side, qty=qty, instance=self.inst, **kw)


def signed(positions: List[dict]) -> float:
    return sum((1 if p.get("side") == "BUY" else -1) * pos_qty(p) for p in positions if p.get("symbol", SYM) == SYM)


def short(email: str) -> str:
    return email.split("@")[0]


def tol(expected: float) -> float:
    return max(2e-3, 0.01 * abs(expected))


def wait_model(x: Ctx, F: Findings, label: str, timeout: float = SYNC_TIMEOUT) -> bool:
    """Poll until every linked follower's net signed qty == master_net x factor. Records lag; HIGH on timeout."""
    t0 = time.time()
    while True:
        mnet = signed(x.positions(x.master))
        data = x.all_positions(x.linked)
        bad = []
        for e in x.linked:
            exp, got = mnet * x.factor[e], signed(data[e])
            if abs(got - exp) > tol(exp):
                bad.append((e, round(exp, 5), round(got, 5)))
        if not bad:
            lag = time.time() - t0
            x.lags.append(lag)
            print(f"    ok   {label}: master net {mnet:+.4f} -> {len(x.linked)} followers match ({lag:.1f}s)")
            return True
        if time.time() - t0 > timeout:
            sample = ", ".join(f"{short(e)} expected {exp} got {got}" for e, exp, got in bad[:5])
            F.add("HIGH", f"{label}: {len(bad)}/{len(x.linked)} followers did not mirror the master within {timeout:.0f}s "
                          f"(master net {mnet:+.4f}). {sample}")
            F.metrics.setdefault("off_model_followers", [short(e) for e, _, _ in bad][:50])
            return False
        time.sleep(0.7)


def need_open(x: Ctx):
    if not x.linked:
        raise SkipStep("no linked followers to check")
    if not x.pos_a:
        raise SkipStep("needs the position opened in E05")


# --------------------------------------------------------------------------------------------- steps
def e01_preflight(x: Ctx, F: Findings):
    import requests
    t = time.perf_counter()
    try:
        r = requests.get(BASE_URL, timeout=15)
        F.metrics["platform_http"] = r.status_code
        if r.status_code >= 500:
            F.add("HIGH", f"platform {BASE_URL} answers HTTP {r.status_code}")
    except Exception as e:
        F.add("HIGH", f"platform {BASE_URL} unreachable: {e}")
        return
    try:
        x.c.get_admin_token()
    except Exception as e:
        F.add("HIGH", f"admin login failed: {e}")

    def login(e):
        try:
            x.c.get_trader_token(e, force_refresh=True)
            return e, None
        except Exception as ex:
            return e, str(ex)[:160]
    with ThreadPoolExecutor(max_workers=10) as ex:
        res = list(ex.map(login, x.everyone))
    failed = [(e, err) for e, err in res if err]
    F.metrics.update(accounts=len(x.everyone), logins_ok=len(x.everyone) - len(failed),
                     login_seconds=round(time.perf_counter() - t, 1))
    if any(e == x.master for e, _ in failed):
        F.add("HIGH", f"master {x.master} cannot log in: {dict(failed)[x.master]}")
    bad_f = [(e, err) for e, err in failed if e != x.master]
    if bad_f:
        F.add("HIGH", f"{len(bad_f)} follower(s) cannot log in, e.g. {short(bad_f[0][0])}: {bad_f[0][1]}")
        F.metrics["login_failures"] = [short(e) for e, _ in bad_f]
    x.logins_ok = not any(e == x.master for e, _ in failed)
    if x.logins_ok:
        x.emails = [e for e in x.emails if e not in dict(bad_f)]


def e02_topology(x: Ctx, F: Findings):
    if not x.logins_ok:
        raise SkipStep("master cannot log in")
    links = x.c.get_copy_followers(x.master, instance=x.inst, active_only=True)
    by_name = {l.get("follower_name"): l for l in links if l.get("master_client_id") in (None, x.master_id)}
    others = [l for l in links if l.get("master_client_id") not in (None, x.master_id)]
    if others:
        F.add("MED", f"master returned {len(others)} links that point at a different master id than MASTER_ID={x.master_id}")
    fm = x.all_funds([x.master] + x.emails)
    m_bal, m_eq = fm[x.master]["balance"] or 1.0, fm[x.master]["equity"] or 1.0
    methods: Dict[str, int] = {}
    unlinked = []
    for e in x.emails:
        l = by_name.get(short(e))
        if not l:
            unlinked.append(short(e))
            continue
        mult = float(l.get("multiplier") or 1.0)
        method = (l.get("method") or "multiplier").lower()
        if method == "balance":
            f = fm[e]["balance"] / m_bal * mult
        elif method == "equity":
            f = fm[e]["equity"] / m_eq * mult
        else:
            f = mult
        if l.get("reverse"):
            f = -f
        x.factor[e], x.link[e] = f, l
        x.linked.append(e)
        key = f"{method} {mult:g}x" + (" reverse" if l.get("reverse") else "")
        methods[key] = methods.get(key, 0) + 1
    F.metrics.update(followers_in_range=len(x.emails), linked=len(x.linked), unlinked=unlinked, link_mix=methods)
    print(f"    {len(x.linked)}/{len(x.emails)} followers linked: {methods}")
    if unlinked:
        F.add("MED", f"{len(unlinked)} follower(s) have NO active copy link and are left out of the checks: {', '.join(unlinked[:10])}"
                     + (" (paper links can no longer be re-created on this platform)" if x.inst == "paper" else ""))
    if not x.linked:
        F.add("HIGH", "no follower in the selected range is linked to the master - nothing to test")


def e03_clean_slate(x: Ctx, F: Findings):
    x.c.teardown_all_accounts(x.master, x.emails, instance=x.inst)
    time.sleep(2.0)
    pos = x.all_positions(x.everyone)
    with_pos = [short(e) for e, p in pos.items() if p]
    pend = {e: p for e, p in x.all_pending(x.everyone).items() if p}
    F.metrics.update(accounts_with_positions=len(with_pos), accounts_with_pending=len(pend))
    if with_pos:
        F.add("HIGH", f"teardown left positions on {len(with_pos)} account(s): {', '.join(with_pos[:8])}")
    if pend:
        F.add("HIGH", f"teardown left pending orders on {len(pend)} account(s): {', '.join(short(e) for e in list(pend)[:8])}")


def _hist_ids(x: Ctx, e: str) -> List[dict]:
    return x.c.get_history(e, x.inst).get("history", []) or []


def e04_baseline(x: Ctx, F: Findings):
    x.base_funds = x.all_funds(x.everyone)
    with ThreadPoolExecutor(max_workers=10) as ex:
        hist = dict(zip(x.everyone, ex.map(lambda e: _hist_ids(x, e), x.everyone)))
    x.hist_mark = {e: max([int(h.get("history_id") or 0) for h in rows] or [0]) for e, rows in hist.items()}
    m = x.base_funds[x.master]
    F.metrics.update(master_balance=round(m["balance"], 2), master_equity=round(m["equity"], 2),
                     follower_balance_min=round(min((x.base_funds[e]["balance"] for e in x.emails), default=0), 2))
    stuck = [short(e) for e, f in x.base_funds.items() if abs(f["used_margin"]) > 0.01]
    if stuck:
        F.add("HIGH", f"margin still in use with no open positions on {len(stuck)} account(s): {', '.join(stuck[:8])}")
    poor = [short(e) for e in x.emails if x.base_funds[e]["balance"] <= 0]
    if poor:
        F.add("MED", f"{len(poor)} follower(s) have zero balance and cannot copy: {', '.join(poor[:8])}")


COPY_REF_SAMPLE = 12      # GET /orders returns an account's ENTIRE order history (no paging/filter), so sample


def _copy_refs_match(x: Ctx, master_ids: set) -> Dict[str, bool]:
    n = len(x.linked)
    picks = x.linked if n <= COPY_REF_SAMPLE else [x.linked[round(i * (n - 1) / (COPY_REF_SAMPLE - 1))] for i in range(COPY_REF_SAMPLE)]

    def has(e):
        for o in x.c.get_orders(e, x.inst).get("orders", [])[:30]:
            ref = str(o.get("copy_ref") or "").lstrip("-")
            if ref and ref in master_ids:
                return True
        return False
    with ThreadPoolExecutor(max_workers=12) as ex:
        return dict(zip(picks, ex.map(has, picks)))


def e05_open(x: Ctx, F: Findings):
    if not x.linked:
        raise SkipStep("no linked followers")
    qty = round(x.a.lot * 2, 6)
    r = x.master_order("BUY", qty)
    x.pos_a = mkt_id(r)
    if r["status_code"] != 200 or not x.pos_a:
        F.add("HIGH", f"master market BUY {qty} rejected: HTTP {r['status_code']} {str(r['data'])[:200]}")
        x.pos_a = None
        return
    d = r["data"]
    x.entry_px = float(getf(d.get("position", {}) or {}, "avg_entry_price", default=0) or getf(d.get("order", {}), "avg_fill_price", default=0) or 0)
    F.metrics.update(master_qty=qty, master_entry=x.entry_px)
    print(f"    master BUY {qty} @ {x.entry_px}")
    wait_model(x, F, f"master BUY {qty}")
    if F.metrics.get("off_model_followers"):
        return
    F.metrics["fanout_seconds"] = round(x.lags[-1], 2)
    ids = {i for i in (x.pos_a, ord_id(r)) if i}
    refs = _copy_refs_match(x, ids)
    missing = [short(e) for e, ok in refs.items() if not ok]
    F.metrics.update(copy_ref_checked=len(refs), copy_ref_ok=len(refs) - len(missing))
    if missing:
        F.add("MED", f"{len(missing)}/{len(refs)} sampled follower copy orders carry no copy_ref back to the master order (audit trail): {', '.join(missing[:8])}")
    slips = []
    for e, ps in x.all_positions(x.linked).items():
        for p in ps:
            px = float(p.get("avg_entry_price") or 0)
            if px and x.entry_px:
                slips.append(px - x.entry_px)
    if slips:
        F.metrics.update(entry_slippage_min=round(min(slips), 2), entry_slippage_max=round(max(slips), 2))
        F.add("INFO", f"follower entry vs master entry: {min(slips):+.1f} .. {max(slips):+.1f} price points")


def _protection(p: dict, key: str) -> Optional[float]:
    v = (p.get(key) or {})
    v = v.get("trigger_price") if isinstance(v, dict) else v
    return round(float(v), 1) if v not in (None, "") else None


def _sync_protection(x: Ctx, F: Findings, label: str, tp: float, sl: float):
    peers = [e for e in x.linked if x.factor[e] > 0]          # reverse followers get mirrored levels; not asserted here
    t0, bad = time.time(), []
    while time.time() - t0 < SYNC_TIMEOUT:
        bad = []
        for e, ps in x.all_positions(peers).items():
            buys = [p for p in ps if p.get("side") == "BUY"]
            if not buys:
                bad.append((e, None, None)); continue
            got = (_protection(buys[0], "tp_order"), _protection(buys[0], "sl_order"))
            if got != (tp, sl):
                bad.append((e, *got))
        if not bad:
            print(f"    ok   {label}: {len(peers)} followers carry TP {tp} / SL {sl} ({time.time() - t0:.1f}s)")
            return
        time.sleep(0.8)
    F.add("HIGH", f"{label}: {len(bad)}/{len(peers)} followers do not carry the master's TP {tp} / SL {sl}; "
                  + ", ".join(f"{short(e)} has TP {a} SL {b}" for e, a, b in bad[:4]))


def _set_protection(x: Ctx, F: Findings, pct: float, label: str):
    need_open(x)
    px = x.entry_px or 0
    if not px:
        raise SkipStep("entry price unknown")
    tp, sl = round(px * (1 + pct), 1), round(px * (1 - pct), 1)
    r = x.c.set_position_protection(x.master, x.pos_a, tp=tp, sl=sl, instance=x.inst)
    if r["status_code"] != 200:
        F.add("HIGH", f"master could not set TP/SL: HTTP {r['status_code']} {str(r['data'])[:200]}")
        return
    mp = next((p for p in x.positions(x.master) if p.get("market_order_id") == x.pos_a), {})
    if (_protection(mp, "tp_order"), _protection(mp, "sl_order")) != (tp, sl):
        F.add("HIGH", f"master read-back shows TP {_protection(mp, 'tp_order')} SL {_protection(mp, 'sl_order')}, expected {tp}/{sl}")
    F.metrics.update(tp=tp, sl=sl)
    _sync_protection(x, F, label, tp, sl)


def e06_set_tpsl(x: Ctx, F: Findings):
    _set_protection(x, F, 0.04, "set TP/SL")


def e07_modify_tpsl(x: Ctx, F: Findings):
    _set_protection(x, F, 0.06, "modify TP/SL")


def e08_partial_close(x: Ctx, F: Findings):
    need_open(x)
    q = round(x.a.lot, 6)
    r = x.c.reduce_position(x.master, x.pos_a, q, instance=x.inst)
    if r["status_code"] != 200:
        F.add("HIGH", f"master partial close of {q} rejected: HTTP {r['status_code']} {str(r['data'])[:200]}")
        return
    left = signed(x.positions(x.master))
    F.metrics["master_net_after_reduce"] = left
    if abs(left - x.a.lot) > 1e-6:
        F.add("HIGH", f"master holds {left} after reducing {q} from {x.a.lot * 2}")
    wait_model(x, F, f"master reduced by {q}")


def e09_pyramid_hedge(x: Ctx, F: Findings):
    need_open(x)
    r1 = x.master_order("BUY", x.a.lot)
    if r1["status_code"] != 200:
        F.add("HIGH", f"master add-on BUY rejected: {str(r1['data'])[:200]}")
    wait_model(x, F, f"add BUY {x.a.lot}")
    r2 = x.master_order("SELL", x.a.lot)
    x.pos_hedge = mkt_id(r2)
    if r2["status_code"] != 200 or not x.pos_hedge:
        F.add("HIGH", f"master SELL hedge leg rejected: {str(r2['data'])[:200]}")
        return
    wait_model(x, F, f"hedge SELL {x.a.lot}")
    legs = {p.get("side") for p in x.positions(x.master)}
    F.metrics["master_sides"] = sorted(legs)
    if legs != {"BUY", "SELL"} and x.inst == "paper":
        F.add("MED", f"paper (hedging) master should hold BUY and SELL legs at once; holds {sorted(legs)}")
    sample = x.linked[0]
    sides = sorted(p.get("side") for p in x.positions(sample))
    F.metrics["sample_follower_legs"] = {short(sample): sides}


def e10_close_one(x: Ctx, F: Findings):
    need_open(x)
    if not x.pos_hedge:
        raise SkipStep("needs the hedge leg from E09")
    r = x.c.squareoff_position(x.master, x.pos_hedge, instance=x.inst)
    if r["status_code"] != 200:
        F.add("HIGH", f"master could not close the hedge leg: {str(r['data'])[:200]}")
        return
    wait_model(x, F, "close the SELL hedge leg only")
    sells = [short(e) for e, ps in x.all_positions(x.linked).items() if x.factor[e] > 0 and any(p.get("side") == "SELL" for p in ps)]
    if sells:
        F.add("HIGH", f"{len(sells)} follower(s) still hold a SELL leg after the master closed its hedge: {', '.join(sells[:8])}")


def e11_close_all(x: Ctx, F: Findings):
    if not x.linked:
        raise SkipStep("no linked followers")
    r = x.c.bulk_squareoff(x.master, instance=x.inst)
    if r["status_code"] != 200:
        F.add("HIGH", f"master close-all rejected: {str(r['data'])[:200]}")
    wait_model(x, F, "master flat")
    time.sleep(1.5)
    fl = x.all_funds(x.everyone)
    stuck = [short(e) for e, f in fl.items() if abs(f["used_margin"]) > 0.01]
    left = [short(e) for e, ps in x.all_positions(x.everyone).items() if ps]
    F.metrics.update(accounts_with_positions=len(left), accounts_with_margin=len(stuck))
    if left:
        F.add("HIGH", f"{len(left)} account(s) still hold positions after the master closed everything: {', '.join(left[:8])}")
    if stuck:
        F.add("HIGH", f"{len(stuck)} account(s) keep margin in use with no positions: {', '.join(stuck[:8])}")
    x.pos_a = x.pos_hedge = None


def e12_pending(x: Ctx, F: Findings):
    if not x.linked:
        raise SkipStep("no linked followers")
    px = x.entry_px
    if not px:
        r = x.master_order("BUY", x.a.lot)
        px = float(getf((r.get("data") or {}).get("position", {}) or {}, "avg_entry_price", default=0) or 0)
        x.c.bulk_squareoff(x.master, instance=x.inst); time.sleep(2.0)
    if not px:
        raise SkipStep("no market price available")
    plan = [("BUY", "LIMIT", 0.7), ("SELL", "LIMIT", 1.3), ("BUY", "STOP", 1.3), ("SELL", "STOP", 0.7)]
    ids = []
    for side, typ, k in plan:
        r = x.c.place_order(x.master, symbol=SYM, side=side, order_type=typ, qty=x.a.lot, price=round(px * k, 1), instance=x.inst)
        oid = ord_id(r)
        if r["status_code"] != 200 or not oid:
            F.add("HIGH", f"far {side} {typ} @ {round(px * k, 1)} rejected: {str(r['data'])[:160]}")
        else:
            ids.append(oid)
    time.sleep(4.0)
    with_pos = [short(e) for e, ps in x.all_positions(x.everyone).items() if ps]
    if with_pos:
        F.add("HIGH", f"{len(with_pos)} account(s) hold positions although no pending order could have filled: {', '.join(with_pos[:8])}")
    copies = {e: len(p) for e, p in x.all_pending(x.linked).items() if p}
    F.metrics.update(master_pending_placed=len(ids), followers_with_pending_copies=len(copies))
    F.add("INFO", f"{len(copies)}/{len(x.linked)} followers received pending copies of the master's {len(ids)} pending orders")
    if 0 < len(copies) < len(x.linked):
        F.add("MED", f"pending orders were copied to only {len(copies)}/{len(x.linked)} followers - copying is inconsistent")
    for oid in ids:
        r = x.c.cancel_order(x.master, oid, instance=x.inst)
        if r["status_code"] != 200:
            F.add("HIGH", f"master could not cancel {oid}: {str(r['data'])[:160]}")
    t0, left = time.time(), {}
    while time.time() - t0 < SYNC_TIMEOUT:
        left = {e: len(p) for e, p in x.all_pending(x.everyone).items() if p}
        if not left:
            break
        time.sleep(1.5)
    F.metrics["accounts_with_leftover_pending"] = len(left)
    if left:
        F.add("HIGH", f"{len(left)} account(s) keep pending orders after the master cancelled all of its own: "
                      + ", ".join(short(e) for e in list(left)[:8]))


def e13_market_types(x: Ctx, F: Findings):
    if not x.linked:
        raise SkipStep("no linked followers")
    try:
        universe = SC.load_symbols()
    except Exception as e:
        F.add("HIGH", f"could not load the platform's symbol list ({SC.symbol_url()}): {e}")
        return
    picks = SC.sample_per_group(universe)
    print(f"    {len(picks)} market groups out of {len(universe)} listed symbols")
    res = SC.sweep(x.c, x.master, x.linked, x.factor, x.inst, picks, batch=20, log=lambda m: print("   ", m))
    groups = SC.summarize(res)
    F.metrics.update(universe=len(universe), groups_tested=len(picks),
                     **{k.lower(): sum(r["status"] == k for r in res) for k in ("PASS", "FAIL", "WARN", "SKIP")},
                     per_group={r["group"]: f"{r['status']} {r['symbol']}" for r in res})
    for r in res:
        if r["status"] == "FAIL":
            F.add("HIGH", f"{r['symbol']} ({r['group']}): {r['detail']}")
        elif r["status"] == "WARN":
            F.add("MED", f"{r['symbol']} ({r['group']}): {r['detail']}")
    closed = [r["group"] for r in res if r["status"] == "SKIP"]
    if closed:
        F.add("INFO", f"market closed now, not tested this run: {', '.join(closed)} "
                      "(re-run in session, e.g. NSE/BSE 03:45-10:00 UTC)")
    if not any(r["status"] == "PASS" for r in res) and not F.items:
        F.add("MED", "every market group was closed - nothing was traded")
    print(f"    {len(groups)} groups: " + ", ".join(f"{g} {'/'.join(k for k, v in c.items() if v)}" for g, c in groups.items()))


def e13_validation(x: Ctx, F: Findings):
    before = len(x.positions(x.master))
    cases = [("qty 0", dict(side="BUY", qty=0)), ("negative qty", dict(side="BUY", qty=-1)),
             ("unknown symbol", dict(side="BUY", qty=x.a.lot, symbol="FAKE:NOPE")), ("bad side", dict(side="HOLD", qty=x.a.lot))]
    results = {}
    for label, kw in cases:
        sym = kw.pop("symbol", SYM)
        r = x.c.place_order(x.master, symbol=sym, instance=x.inst, **kw)
        code = r["status_code"]
        results[label] = code
        if code >= 500:
            F.add("HIGH", f"{label}: server error HTTP {code} (must be a 4xx validation error)")
        elif code < 400:
            F.add("HIGH", f"{label}: ACCEPTED with HTTP {code} - invalid order must be rejected")
    F.metrics["http_codes"] = results
    time.sleep(2.5)
    after = len(x.positions(x.master))
    leaked = [short(e) for e, ps in x.all_positions(x.linked).items() if ps]
    if after != before or leaked:
        F.add("HIGH", f"an invalid order created positions (master {before}->{after}, followers {len(leaked)})")
        x.c.teardown_all_accounts(x.master, x.emails, instance=x.inst)


def e14_accounting(x: Ctx, F: Findings):
    if not x.hist_mark:
        raise SkipStep("needs the E04 baseline")
    time.sleep(1.0)
    accounts = [x.master] + x.linked
    with ThreadPoolExecutor(max_workers=10) as ex:
        hist = dict(zip(accounts, ex.map(lambda e: _hist_ids(x, e), accounts)))
    now = x.all_funds(accounts)
    try:
        meta = SC.symbol_meta()
    except Exception:
        meta = {}
    bad_rows, bad_bal, pnl = [], [], {}
    converted: Dict[str, List[tuple]] = {}
    for e in accounts:
        rows = [h for h in hist[e] if int(h.get("history_id") or 0) > x.hist_mark.get(e, 0)]
        total = 0.0
        for h in rows:
            got = float(h.get("realized_pnl") or 0)
            total += got
            m = meta.get(h.get("symbol"))
            want = SC.expected_pnl(h, m)
            if want is None:                       # currency-converted pair: checked for consistency below
                converted.setdefault(h.get("symbol"), []).append((short(e), h))
            elif abs(got - want) > SC.pnl_tolerance(m, want):
                bad_rows.append(f"{short(e)} {h.get('symbol')} {h.get('side')} {h.get('qty')} {h.get('entry_price')}->{h.get('exit_price')}"
                                f" x contract {(m or {}).get('csize', 1):g}: realized {got} expected {round(want, 4)}")
        pnl[e] = total
    for sym, rows in converted.items():
        bad_rows += [f"{sym}: {msg}" for msg in SC.converted_pnl_issues(rows)]
        delta = now[e]["balance"] - x.base_funds.get(e, {}).get("balance", now[e]["balance"])
        if abs(delta - total) > 0.05:
            bad_bal.append(f"{short(e)} balance moved {delta:+.4f} but its closed trades realized {total:+.4f}")
        if abs(now[e]["equity"] - now[e]["balance"]) > 0.01:
            bad_bal.append(f"{short(e)} equity {now[e]['equity']:.2f} != balance {now[e]['balance']:.2f} while flat")
    m_trades = len([h for h in hist[x.master] if int(h.get("history_id") or 0) > x.hist_mark.get(x.master, 0)])
    F.metrics.update(master_closed_trades=m_trades, master_realized_pnl=round(pnl[x.master], 4),
                     follower_realized_pnl_min=round(min((pnl[e] for e in x.linked), default=0), 4),
                     follower_realized_pnl_max=round(max((pnl[e] for e in x.linked), default=0), 4))
    if m_trades == 0:
        F.add("MED", "no new closed trades found in the master's history - did the trade steps run?")
    if bad_rows:
        F.add("HIGH", f"{len(bad_rows)} closed trade(s) with wrong realized PnL, e.g. " + "; ".join(bad_rows[:3]))
    if bad_bal:
        F.add("HIGH", f"{len(bad_bal)} account(s) whose balance does not reconcile, e.g. " + "; ".join(bad_bal[:3]))
    no_hist = [short(e) for e in x.linked if m_trades and not [h for h in hist[e] if int(h.get("history_id") or 0) > x.hist_mark.get(e, 0)]]
    if no_hist:
        F.add("HIGH", f"{len(no_hist)} follower(s) have no closed copy trades in history although the master closed {m_trades}: {', '.join(no_hist[:8])}")
    F.add("INFO", f"realized PnL this run: master {pnl[x.master]:+.4f}; followers "
                  f"{F.metrics['follower_realized_pnl_min']:+.4f} .. {F.metrics['follower_realized_pnl_max']:+.4f}")
    # Copy fidelity: a follower's PnL differs from master PnL x factor only by its own fill prices (slippage).
    gaps = {e: pnl[e] - pnl[x.master] * x.factor[e] for e in x.linked}
    if gaps:
        worst = max(gaps, key=lambda e: abs(gaps[e]))
        F.metrics.update(pnl_gap_vs_master_max=round(gaps[worst], 4), pnl_gap_worst_follower=short(worst))
        F.add("INFO", f"copy fidelity: follower PnL minus (master PnL x factor) is at most {gaps[worst]:+.4f} "
                      f"({short(worst)}) - caused by followers filling at different prices than the master")


def e15_final_audit(x: Ctx, F: Findings):
    x.c.teardown_all_accounts(x.master, x.emails, instance=x.inst)
    time.sleep(2.0)
    pos = x.all_positions(x.everyone)
    fl = x.all_funds(x.everyone)
    pend = {e: p for e, p in x.all_pending(x.everyone).items() if p}
    issues = []
    for e in x.everyone:
        f = fl[e]
        if pos[e]:
            issues.append(f"{short(e)}: {len(pos[e])} open position(s)")
        if e in pend:
            issues.append(f"{short(e)}: {len(pend[e])} pending order(s)")
        if abs(f["used_margin"]) > 0.01:
            issues.append(f"{short(e)}: used margin {f['used_margin']:.2f}")
        if abs(f["equity"] - f["balance"]) > 0.01:
            issues.append(f"{short(e)}: equity {f['equity']:.2f} != balance {f['balance']:.2f}")
    F.metrics.update(accounts_checked=len(x.everyone), issues=len(issues))
    if issues:
        F.add("HIGH", f"{len(issues)} leftover(s) after the run: " + "; ".join(issues[:6]))


STEPS: List[tuple] = [
    ("E01", "Preflight: platform + logins", e01_preflight, True),
    ("E02", "Copy topology (who is linked)", e02_topology, True),
    ("E03", "Clean slate", e03_clean_slate, True),
    ("E04", "Baseline snapshot", e04_baseline, True),
    ("E05", "Open market BUY & fan-out", e05_open, False),
    ("E06", "Set TP/SL syncs to followers", e06_set_tpsl, False),
    ("E07", "Modify TP/SL re-syncs", e07_modify_tpsl, False),
    ("E08", "Partial close mirrors", e08_partial_close, False),
    ("E09", "Pyramid + hedge leg mirror", e09_pyramid_hedge, False),
    ("E10", "Close one position", e10_close_one, False),
    ("E11", "Close all -> everyone flat", e11_close_all, False),
    ("E12", "Pending orders place + cancel", e12_pending, False),
    ("E13", "Every market type (symbol sweep)", e13_market_types, False),
    ("E14", "Invalid orders rejected", e13_validation, False),
    ("E15", "Accounting reconciles", e14_accounting, False),
    ("E16", "Final audit (clean accounts)", e15_final_audit, True),
]
FINAL_STEP = STEPS[-1][0]


def run_step(x: Ctx, sid: str, name: str, fn: Callable) -> Dict[str, Any]:
    print(f"\n[{sid}] {name}")
    F = Findings(f"{sid} {name}")
    t0 = time.time()
    try:
        fn(x, F)
        res = F.result()
    except SkipStep as s:
        F.add("INFO", f"skipped: {s}")
        res = F.result("SKIP")
    except Exception as e:
        F.add("HIGH", f"runner exception: {type(e).__name__}: {e}")
        res = F.result("ERROR")
    res.update(id=sid, title=name, seconds=round(time.time() - t0, 1))
    marker = {"PASS": "[PASS]", "FAIL": "[FAIL]", "ERROR": "[FAIL]", "WARN": "[WARN]", "SKIP": "[SKIP]"}[res["status"]]
    print(f"{marker} {sid} {name} ({res['seconds']}s)")
    return res


# --------------------------------------------------------------------------------------------- reports
def write_reports(results: List[Dict[str, Any]], x: Ctx, started: datetime) -> Path:
    ts = started.strftime("%Y%m%d_%H%M%S")
    out = BASE_DIR / "reports" / "evidence"
    out.mkdir(parents=True, exist_ok=True)
    tally: Dict[str, int] = {}
    for r in results:
        tally[r["status"]] = tally.get(r["status"], 0) + 1
    verdict = "FAIL" if tally.get("FAIL") or tally.get("ERROR") else ("WARN" if tally.get("WARN") else "PASS")
    meta = {"suite": "End-to-End Copy-Trading Test", "verdict": verdict, "timestamp": datetime.now(timezone.utc).isoformat(),
            "started": started.isoformat(timespec="seconds"), "duration_sec": round((datetime.now() - started).total_seconds(), 1),
            "instance": x.inst, "platform": BASE_URL, "master": x.master, "master_id": x.master_id,
            "followers_range": [x.a.start, x.a.end], "followers_linked": len(x.linked), "lot": x.a.lot,
            "max_sync_seconds": round(max(x.lags), 2) if x.lags else None, "tally": tally, "results": results}
    jp, mp = out / f"e2e_evidence_{ts}.json", out / f"e2e_evidence_{ts}.md"
    jp.write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    icon = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌", "SKIP": "⏭️", "ERROR": "💥"}
    lines = [f"# End-to-End Copy-Trading Test - {icon[verdict]} {verdict}", "",
             f"**Run:** {meta['started']} ({meta['duration_sec']}s) | **Instance:** `{x.inst}` | **Platform:** {BASE_URL}  ",
             f"**Master:** {x.master} | **Followers:** {x.a.start}-{x.a.end} ({len(x.linked)} linked) | **Lot:** {x.a.lot}"
             + (f" | **Slowest follower sync:** {meta['max_sync_seconds']}s" if x.lags else ""), "",
             "| Step | Check | Result | Time | Findings |", "| :--- | :--- | :---: | ---: | :--- |"]
    for r in results:
        msgs = [f"{f['severity']}: {f['message']}" for f in r["findings"] if f["severity"] != "INFO"]
        lines.append(f"| {r['id']} | {r['title']} | {icon.get(r['status'], '?')} {r['status']} | {r['seconds']}s | "
                     + ("<br>".join(m.replace("|", "/") for m in msgs[:3]) or "-") + " |")
    lines += ["", "## Details", ""]
    for r in results:
        lines.append(f"### {r['id']} {r['title']} - {r['status']}")
        lines += [f"- **{f['severity']}** {f['message']}" for f in r["findings"]] or ["- no findings"]
        if r.get("metrics"):
            lines.append(f"- metrics: `{json.dumps(r['metrics'], default=str)[:600]}`")
        lines.append("")
    lines += ["## How to read this", "",
              "- **FAIL** - an invariant was broken: the platform did something wrong. File a bug with the finding text.",
              "- **WARN** - suspicious or incomplete (e.g. some followers not linked). Check before sign-off.",
              "- **SKIP** - an earlier step failed, so this one could not run.",
              "- Re-run a step: `python test_suite/e2e_runner.py --only E06` (setup E01-E04 and the final audit always run).",
              "- E13 covers one symbol per market group; for every listed symbol run the **All Symbols** suite "
              "(`python test_suite/symbol_coverage_runner.py`)."]
    mp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return mp


# --------------------------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description="End-to-end copy-trading test (master -> followers, full trade lifecycle)")
    ap.add_argument("--master", default=MASTER_EMAIL)
    ap.add_argument("--master-id", default=MASTER_ID)
    ap.add_argument("--prefix", default=DEFAULT_PREFIX)
    ap.add_argument("--domain", default=DEFAULT_DOMAIN)
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int, default=FOLLOWER_COUNT)
    ap.add_argument("--instance", default="paper", choices=["paper", "real"])
    ap.add_argument("--lot", type=float, default=0.1, help="base lot; the master opens 2x this, then reduces/adds/hedges by 1x")
    ap.add_argument("--only", default="", help="comma list of steps, e.g. E05,E06 (E01-E04 and the final audit always run)")
    ap.add_argument("--i-understand-real-money", action="store_true")
    a = ap.parse_args()
    if a.instance != "paper" and not a.i_understand_real_money:
        print("Refusing to run on the REAL instance without --i-understand-real-money"); return 2
    if a.lot <= 0:
        print("--lot must be > 0"); return 2
    if a.end < a.start:
        a.start, a.end = a.end, a.start
    emails = [f"{a.prefix}{i}@{a.domain}" for i in range(a.start, a.end + 1)]
    wanted = {s.strip().upper() for s in a.only.split(",") if s.strip()}

    started = datetime.now()
    print("=" * 80)
    print(f" END-TO-END COPY-TRADING TEST | {a.instance.upper()} | master {a.master} | followers {a.start}-{a.end} | lot {a.lot}")
    print("=" * 80)
    c = BlackTraderClient(base_url=BASE_URL, max_workers=10)
    x = Ctx(c, a, emails)
    results: List[Dict[str, Any]] = []
    try:
        for sid, name, fn, always in STEPS:
            if wanted and sid not in wanted and not always:
                continue
            res = run_step(x, sid, name, fn)
            results.append(res)
            if sid == "E01" and not x.logins_ok:
                print("[!] Master cannot log in - stopping. Fix the credentials (Getting Started tab / scripts/doctor.py).")
                break
    finally:
        if x.logins_ok and (not results or results[-1]["id"] != FINAL_STEP):
            try:
                x.c.teardown_all_accounts(x.master, x.emails, instance=x.inst)
            except Exception as e:
                print(f"[!] final teardown failed: {e}")
        mp = write_reports(results, x, started)

    tally: Dict[str, int] = {}
    for r in results:
        tally[r["status"]] = tally.get(r["status"], 0) + 1
    print("\n" + "=" * 80)
    print(" STEP                                      RESULT")
    for r in results:
        print(f"  {r['id']}  {r['title']:<38} {r['status']}")
    print(f"\n SUMMARY: {tally}")
    print(f" Report : {mp}")
    print("=" * 80)
    return 1 if tally.get("FAIL") or tally.get("ERROR") else 0


if __name__ == "__main__":
    sys.exit(main())
