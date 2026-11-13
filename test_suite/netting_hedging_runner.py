#!/usr/bin/env python3
"""
BlackTrader Netting vs Hedging Suite (paper, paper-net, real, real-net)
=======================================================================
The platform has four trading instances:

    paper      hedging   simulated        paper-net   netting   simulated
    real       hedging   "real" wallet    real-net    netting   "real" wallet

HEDGING keeps every order as its own position (BUY and SELL legs coexist).
NETTING keeps ONE position per symbol: an opposite order reduces it, and a larger
opposite order flips it.  This suite proves both behaviours on the master and proves
that every follower ends up exactly where the master's position x the follower's link
multiplier says it must be (long total and short total are compared separately, so the
same model covers both modes).

Hedging scenarios        H1 BUY+SELL legs coexist   H2 close one leg   H3 partial reduce leg   H4 close all
Netting scenarios        N1 open                    N2 opposite order reduces (still ONE position)
                         N3 oversized opposite order FLIPS side         N4 exact opposite closes   N5 TP/SL on netted position
Both                     P1 pending order fan-out + cancel     C1 concurrent mixed BUY/SELL race

Copy trading needs links on the instance.  Paper links already exist (the platform no longer
creates them) and are only used as they are.  paper-net has no links, so it runs master-only.
On real / real-net the suite creates temporary links + wallets for the first --followers
accounts, and removes the links it created when it is done.

Safety: refuses to run if the master or any follower is A-book (orders could reach a broker),
unless --allow-a-book is passed.  Only the chosen --symbol is ever touched.

Usage:
    python test_suite/netting_hedging_runner.py --instances paper,paper-net --followers 10
    python test_suite/netting_hedging_runner.py --instances real,real-net --followers 10
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config.settings import BASE_URL, DEFAULT_PREFIX, DEFAULT_DOMAIN, MASTER_EMAIL, MASTER_ID
from test_suite.client import BlackTraderClient
from test_suite.breakpoint_race_runner import mkt_id, ord_id, getf, pos_qty, parallel

INSTANCES = ("paper", "paper-net", "real", "real-net")
FACTORS = [1.0, 2.0, 3.0, 0.5]          # multipliers given to links this suite creates
WALLET = 1_000_000.0
TOL = 1e-4


def is_netting(inst: str) -> bool:
    return inst.endswith("-net")


def mode_name(inst: str) -> str:
    return "NETTING" if is_netting(inst) else "HEDGING"


class Ctx:
    def __init__(self, c, inst, symbol, lot, master, emails, factors):
        self.c, self.inst, self.symbol, self.lot = c, inst, symbol, lot
        self.master, self.emails, self.factors = master, emails, factors   # factors: email -> link multiplier

    @property
    def copy(self) -> bool:
        return bool(self.emails)


# --------------------------------------------------------------------------- account helpers
def sym_positions(ctx: Ctx, email: str) -> List[dict]:
    ps = ctx.c.get_positions(email, ctx.inst).get("positions", []) or []
    return [p for p in ps if p.get("symbol") == ctx.symbol]


def totals(ctx: Ctx, email: str) -> Tuple[float, float, int]:
    """(long qty, short qty, number of positions) for the test symbol."""
    buy = sell = 0.0
    ps = sym_positions(ctx, email)
    for p in ps:
        if str(p.get("side", "")).upper() == "BUY":
            buy += pos_qty(p)
        else:
            sell += pos_qty(p)
    return round(buy, 8), round(sell, 8), len(ps)


def flatten(ctx: Ctx):
    """Close positions and cancel pending orders of the test symbol on master + followers."""
    for email in [ctx.master] + ctx.emails:
        for p in sym_positions(ctx, email):
            mid = p.get("market_order_id")
            if mid:
                ctx.c.squareoff_position(email, mid, ctx.inst)
        for o in (ctx.c.get_orders(email, ctx.inst).get("orders", []) or []):
            if o.get("symbol") == ctx.symbol and o.get("state") == "PENDING":
                ctx.c.cancel_order(email, o.get("order_id"), ctx.inst)
    time.sleep(1.0)


def check_followers(ctx: Ctx, timeout: float = 25.0) -> Tuple[bool, List[str], Tuple[float, float, int]]:
    """Poll until every follower matches master totals x multiplier (or timeout)."""
    mbuy, msell, mpos = totals(ctx, ctx.master)
    t0, bad = time.time(), []
    while True:
        bad = []
        for email in ctx.emails:
            f = ctx.factors[email]
            fb, fs, fp = totals(ctx, email)
            if abs(fb - mbuy * f) > max(TOL, 0.01 * mbuy * f) or abs(fs - msell * f) > max(TOL, 0.01 * msell * f):
                bad.append(f"{email.split('@')[0]} x{f}: has long {fb}/short {fs}, expected long {mbuy * f:.4f}/short {msell * f:.4f}")
            elif is_netting(ctx.inst) and fp > 1:
                bad.append(f"{email.split('@')[0]}: {fp} positions on a NETTING account (expected <=1)")
        if not bad or time.time() - t0 > timeout:
            break
        time.sleep(1.0)
        mbuy, msell, mpos = totals(ctx, ctx.master)
    return (not bad), bad, (mbuy, msell, mpos)


def buy(ctx, qty, **kw):
    return ctx.c.place_order(ctx.master, ctx.symbol, "BUY", "MARKET", qty, instance=ctx.inst, **kw)


def sell(ctx, qty, **kw):
    return ctx.c.place_order(ctx.master, ctx.symbol, "SELL", "MARKET", qty, instance=ctx.inst, **kw)


def need_ok(res, what):
    if res.get("status_code") != 200:
        raise AssertionError(f"{what} rejected: HTTP {res.get('status_code')} {str(res.get('data'))[:160]}")
    return res


class Check:
    """Collects assertions for one scenario."""
    def __init__(self, name):
        self.name, self.fails, self.notes = name, [], []

    def eq(self, label, got, exp):
        ok = abs(got - exp) <= TOL if isinstance(got, float) or isinstance(exp, float) else got == exp
        (self.notes if ok else self.fails).append(f"{label}: got {got}, expected {exp}" if not ok else f"{label} = {got}")
        return ok

    def true(self, label, cond, detail=""):
        (self.notes if cond else self.fails).append(label if cond else f"{label} {detail}".strip())
        return cond

    def followers(self, ctx, label="followers match model"):
        if not ctx.copy:
            self.notes.append(f"{label}: skipped (no followers on this instance)")
            return
        ok, bad, (b, s, n) = check_followers(ctx)
        if ok:
            self.notes.append(f"{label}: {len(ctx.emails)}/{len(ctx.emails)} OK (master long {b}, short {s}, {n} pos)")
        else:
            self.fails.append(f"{label}: {len(bad)}/{len(ctx.emails)} wrong - " + " | ".join(bad[:4]))

    def result(self):
        status = "FAIL" if self.fails else "PASS"
        print(f"  => {self.name}: {status}")
        for f in self.fails:
            print(f"     [FAIL] {f}")
        return {"name": self.name, "status": status, "failures": self.fails, "notes": self.notes}


def run(name, fn, ctx):
    print(f"\n[{name}]")
    chk = Check(name)
    try:
        fn(ctx, chk)
    except AssertionError as e:
        chk.fails.append(str(e))
    except Exception as e:                       # never let one scenario stop the suite
        chk.fails.append(f"EXC {type(e).__name__}: {e}")
    finally:
        flatten(ctx)
    return chk.result()


# --------------------------------------------------------------------------- hedging scenarios
def h1_legs(ctx, k):
    need_ok(buy(ctx, ctx.lot), "BUY"); need_ok(sell(ctx, ctx.lot), "SELL")
    time.sleep(1.5)
    b, s, n = totals(ctx, ctx.master)
    k.eq("master positions (BUY leg + SELL leg stay separate)", n, 2)
    k.eq("master long", b, ctx.lot); k.eq("master short", s, ctx.lot)
    k.followers(ctx)


def h2_close_leg(ctx, k):
    r = need_ok(buy(ctx, ctx.lot), "BUY"); need_ok(sell(ctx, ctx.lot), "SELL")
    time.sleep(1.5)
    need_ok(ctx.c.squareoff_position(ctx.master, mkt_id(r), ctx.inst), "close BUY leg")
    time.sleep(1.5)
    b, s, n = totals(ctx, ctx.master)
    k.eq("master long after closing BUY leg", b, 0.0); k.eq("master short kept", s, ctx.lot); k.eq("master positions", n, 1)
    k.followers(ctx)


def h3_reduce_leg(ctx, k):
    need_ok(buy(ctx, ctx.lot), "BUY"); r = need_ok(sell(ctx, ctx.lot), "SELL")
    time.sleep(1.5)
    need_ok(ctx.c.reduce_position(ctx.master, mkt_id(r), ctx.lot / 2, ctx.inst), "reduce SELL leg")
    time.sleep(1.5)
    b, s, n = totals(ctx, ctx.master)
    k.eq("master long untouched", b, ctx.lot); k.eq("master short reduced by half", s, ctx.lot / 2)
    k.followers(ctx)


def h4_close_all(ctx, k):
    need_ok(buy(ctx, ctx.lot), "BUY"); need_ok(sell(ctx, ctx.lot * 2), "SELL")
    time.sleep(1.5)
    ctx.c.bulk_squareoff(ctx.master, ctx.inst)
    time.sleep(2.0)
    k.eq("master positions after close all", totals(ctx, ctx.master)[2], 0)
    k.followers(ctx, "followers flat")


# --------------------------------------------------------------------------- netting scenarios
def n1_open(ctx, k):
    need_ok(buy(ctx, ctx.lot * 3), "BUY 3L"); time.sleep(1.5)
    b, s, n = totals(ctx, ctx.master)
    k.eq("master positions", n, 1); k.eq("master long", b, ctx.lot * 3)
    k.followers(ctx)


def n2_reduce(ctx, k):
    need_ok(buy(ctx, ctx.lot * 3), "BUY 3L"); time.sleep(1.5)
    need_ok(sell(ctx, ctx.lot), "SELL 1L"); time.sleep(1.5)
    b, s, n = totals(ctx, ctx.master)
    k.eq("master positions (opposite order must NET, not open a 2nd leg)", n, 1)
    k.eq("master long reduced to 2L", b, ctx.lot * 2); k.eq("master short", s, 0.0)
    k.followers(ctx)


def n3_flip(ctx, k):
    need_ok(buy(ctx, ctx.lot * 3), "BUY 3L"); time.sleep(1.5)
    need_ok(sell(ctx, ctx.lot * 5), "SELL 5L"); time.sleep(1.5)
    b, s, n = totals(ctx, ctx.master)
    k.eq("master positions after flip", n, 1)
    k.eq("master long after flip", b, 0.0); k.eq("master short = 5L - 3L", s, ctx.lot * 2)
    k.followers(ctx)


def n4_close_by_opposite(ctx, k):
    need_ok(buy(ctx, ctx.lot * 2), "BUY 2L"); time.sleep(1.5)
    need_ok(sell(ctx, ctx.lot * 2), "SELL 2L"); time.sleep(1.5)
    k.eq("master positions (exact opposite order closes)", totals(ctx, ctx.master)[2], 0)
    k.followers(ctx, "followers flat")


def n5_protection(ctx, k):
    r = need_ok(buy(ctx, ctx.lot * 2), "BUY 2L"); time.sleep(1.5)
    p = sym_positions(ctx, ctx.master)[0]
    px = float(p.get("avg_entry_price") or p.get("current_price") or 0)
    tp, sl = round(px * 1.10, 2), round(px * 0.90, 2)
    need_ok(ctx.c.set_position_protection(ctx.master, p["market_order_id"], tp=tp, sl=sl, instance=ctx.inst), "set TP/SL")
    need_ok(buy(ctx, ctx.lot), "add BUY 1L to netted position"); time.sleep(2.0)
    p = sym_positions(ctx, ctx.master)[0]
    mtp = (p.get("tp_order") or {}).get("trigger_price"); msl = (p.get("sl_order") or {}).get("trigger_price")
    k.true("master TP/SL survive adding to the netted position", mtp == tp and msl == sl, f"(tp {mtp} sl {msl}, expected {tp}/{sl})")
    k.eq("master netted size", pos_qty(p), ctx.lot * 3)
    k.followers(ctx)
    bad = _protection_mismatch(ctx, mtp, msl)
    if ctx.copy:
        k.true(f"follower TP/SL equal master after add ({len(ctx.emails) - len(bad)}/{len(ctx.emails)})", not bad, "; ".join(bad[:4]))


def h5_protection(ctx, k):
    need_ok(buy(ctx, ctx.lot * 2), "BUY 2L"); time.sleep(1.5)
    p = sym_positions(ctx, ctx.master)[0]
    px = float(p.get("avg_entry_price") or p.get("current_price") or 0)
    tp, sl = round(px * 1.10, 2), round(px * 0.90, 2)
    need_ok(ctx.c.set_position_protection(ctx.master, p["market_order_id"], tp=tp, sl=sl, instance=ctx.inst), "set TP/SL")
    time.sleep(2.5)
    p = sym_positions(ctx, ctx.master)[0]
    mtp = (p.get("tp_order") or {}).get("trigger_price"); msl = (p.get("sl_order") or {}).get("trigger_price")
    k.true("master TP/SL stored", mtp == tp and msl == sl, f"(tp {mtp} sl {msl}, expected {tp}/{sl})")
    k.followers(ctx)
    bad = _protection_mismatch(ctx, mtp, msl)
    if ctx.copy:
        k.true(f"follower TP/SL equal master ({len(ctx.emails) - len(bad)}/{len(ctx.emails)})", not bad, "; ".join(bad[:4]))


def _protection_mismatch(ctx, mtp, msl):
    bad = []
    for email in ctx.emails:
        fp = sym_positions(ctx, email)
        if not fp:
            bad.append(email.split("@")[0] + " (no position)"); continue
        ftp = (fp[0].get("tp_order") or {}).get("trigger_price"); fsl = (fp[0].get("sl_order") or {}).get("trigger_price")
        if mtp is not None and (ftp != mtp or fsl != msl):
            bad.append(f"{email.split('@')[0]} tp {ftp} sl {fsl}")
    return bad


# --------------------------------------------------------------------------- scenarios for both modes
def p1_pending(ctx, k):
    # learn the last price from a throw-away 1-lot position, then price the limits far below it
    need_ok(buy(ctx, ctx.lot), "probe BUY"); time.sleep(1.0)
    p = sym_positions(ctx, ctx.master)[0]; last = float(p.get("current_price") or p.get("avg_entry_price"))
    ctx.c.squareoff_position(ctx.master, p["market_order_id"], ctx.inst); time.sleep(1.5)
    ids = []
    for i in range(3):
        res = ctx.c.place_order(ctx.master, ctx.symbol, "BUY", "LIMIT", ctx.lot, price=round(last * (0.80 - i * 0.01), 2), instance=ctx.inst)
        if ord_id(res): ids.append(ord_id(res))
    k.eq("master pending orders placed", len(ids), 3)
    time.sleep(2.5)
    if ctx.copy:
        short = [e for e in ctx.emails
                 if sum(1 for o in (ctx.c.get_orders(e, ctx.inst).get("orders", []) or [])
                        if o.get("symbol") == ctx.symbol and o.get("state") == "PENDING") != 3]
        k.true(f"pending orders fanned out to followers ({len(ctx.emails) - len(short)}/{len(ctx.emails)})", not short,
               ", ".join(s.split("@")[0] for s in short[:5]))
        if short:
            time.sleep(8.0)      # rule out slow fan-out
            late = [e for e in short if sum(1 for o in (ctx.c.get_orders(e, ctx.inst).get("orders", []) or [])
                                            if o.get("symbol") == ctx.symbol and o.get("state") == "PENDING") == 3]
            k.notes.append(f"diagnostic: {len(late)}/{len(short)} of the missing followers got the orders within 10 s more")
            sample = [(o.get("state"), o.get("type"), o.get("side"), o.get("qty")) for o in
                      (ctx.c.get_orders(short[0], ctx.inst).get("orders", []) or []) if o.get("symbol") == ctx.symbol][:4]
            k.notes.append(f"diagnostic: {short[0].split('@')[0]} orders on {ctx.symbol}: {sample}")
    for i in ids:
        ctx.c.cancel_order(ctx.master, i, ctx.inst)
    time.sleep(2.0)
    left = [e for e in [ctx.master] + ctx.emails
            if any(o.get("symbol") == ctx.symbol and o.get("state") == "PENDING" for o in (ctx.c.get_orders(e, ctx.inst).get("orders", []) or []))]
    k.true("all pending orders cancelled everywhere", not left, ", ".join(x.split("@")[0] for x in left[:5]))


def c1_race(ctx, k):
    """6 BUY + 4 SELL released at the same instant; followers must equal master x multiplier afterwards."""
    res = parallel(lambda i: buy(ctx, ctx.lot) if i < 6 else sell(ctx, ctx.lot), 10)
    k.eq("orders accepted", sum(1 for r in res if r.get("status_code") == 200), 10)
    k.true("no 5xx under concurrent BUY/SELL", not any(int(r.get("status_code", 0)) >= 500 for r in res))
    time.sleep(3.0)
    b, s, n = totals(ctx, ctx.master)
    if is_netting(ctx.inst):
        k.true("master holds <=1 position (netting invariant)", n <= 1, f"(has {n})")
        k.true("netting result is one-sided", b == 0.0 or s == 0.0, f"(long {b}, short {s})")
        k.eq("master net equals 6L - 4L", round(b - s, 8), ctx.lot * 2)
    else:
        k.eq("master hedging legs", n, 10); k.eq("master long", b, ctx.lot * 6); k.eq("master short", s, ctx.lot * 4)
    k.followers(ctx)


SCENARIOS_HEDGE = [("H1 BUY and SELL legs coexist", h1_legs), ("H2 close one leg", h2_close_leg),
                   ("H3 partial reduce of one leg", h3_reduce_leg), ("H4 close all", h4_close_all), ("H5 TP/SL sync", h5_protection),
                   ("P1 pending fan-out + cancel", p1_pending), ("C1 concurrent BUY/SELL race", c1_race)]
SCENARIOS_NET = [("N1 open netted position", n1_open), ("N2 opposite order reduces (one position)", n2_reduce),
                 ("N3 oversized opposite order flips", n3_flip), ("N4 exact opposite order closes", n4_close_by_opposite),
                 ("N5 TP/SL on netted position survives add", n5_protection),
                 ("P1 pending fan-out + cancel", p1_pending), ("C1 concurrent BUY/SELL race", c1_race)]


# --------------------------------------------------------------------------- setup / teardown
def instance_setup(c, inst, master, n_followers, allow_a_book) -> Tuple[List[str], Dict[str, float], List[str], str]:
    """Return (follower emails used, email->multiplier, links created, note)."""
    books = c.get_member_books()
    if not allow_a_book and books.get(master, {}).get("book") != "b":
        raise SystemExit(f"[ABORT] master {master} is not B-book ({books.get(master)}); pass --allow-a-book to override")
    all_links = {l["follower_name"]: l for l in c.get_copy_followers(master, inst, active_only=False)}
    existing = {n: l for n, l in all_links.items() if l.get("instance") == inst and l.get("status") == "active"}
    created: List[str] = []
    emails = [f"{DEFAULT_PREFIX}{i}@{DEFAULT_DOMAIN}" for i in range(1, n_followers + 1)]
    if inst not in ("paper", "paper-net"):
        # A follower has ONE link record per master, whatever the instance: `follow` on another instance CONVERTS an
        # active link (e.g. paper -> real) and `unfollow` then ENDS it - and paper links can never be re-created.
        # So never touch a follower that is actively linked on a different instance.
        taken = [e for e in emails if all_links.get(e.split("@")[0], {}).get("status") == "active"
                 and all_links[e.split("@")[0]].get("instance") != inst]
        if taken:
            print(f"[!] skipping {len(taken)} follower(s) with an ACTIVE link on another instance (would be converted/ended): "
                  + ", ".join(t.split("@")[0] for t in taken[:6]) + (" ..." if len(taken) > 6 else ""))
        emails = [e for e in emails if e not in taken]
    if inst == "paper":
        emails = [e for e in emails if e.split("@")[0] in existing]          # links cannot be created on paper
        note = "paper links exist already; none created"
    elif inst == "paper-net":
        return [], {}, [], "paper-net: platform refuses to create copy links on paper accounts -> master-only netting tests"
    else:
        note = "temporary links + wallets created for this run"
        # master wallet
        mrow = books[master]
        if float((c.get_positions(master, inst).get("funds") or {}).get("balance", 0) or 0) <= 0:
            c.set_member_balance(mrow["member_id"], WALLET, inst)
        for idx, e in enumerate(list(emails)):
            if not allow_a_book and books.get(e, {}).get("book") != "b":
                raise SystemExit(f"[ABORT] {e} is not B-book; pass --allow-a-book to override")
            if float((c.get_positions(e, inst).get("funds") or {}).get("balance", 0) or 0) <= 0:
                c.set_member_balance(books[e]["member_id"], WALLET, inst)
            if e.split("@")[0] not in existing:
                r = c.follow_master(e, MASTER_ID, instance=inst, method="multiplier", multiplier=FACTORS[idx % 4])
                if r.get("status_code") != 200:
                    raise SystemExit(f"[ABORT] cannot create {inst} link for {e}: HTTP {r.get('status_code')} {str(r.get('data'))[:200]}")
                created.append(e)
        time.sleep(2.0)
        existing = {l["follower_name"]: l for l in c.get_copy_followers(master, inst, active_only=True) if l.get("instance") == inst}
    factors = {e: float(existing[e.split("@")[0]]["multiplier"]) for e in emails if e.split("@")[0] in existing}
    return [e for e in emails if e in factors], factors, created, note


def run_instance(c, inst, args) -> Dict[str, Any]:
    print("\n" + "=" * 80)
    print(f" {inst.upper()}  ({mode_name(inst)})  symbol={args.symbol} lot={args.lot}")
    print("=" * 80)
    emails, factors, created, note = instance_setup(c, inst, args.master, args.followers, args.allow_a_book)
    print(f"[*] {note}")
    print(f"[*] followers under test: {len(emails)}  multipliers: {sorted(set(factors.values()))}")
    ctx = Ctx(c, inst, args.symbol, args.lot, args.master, emails, factors)
    results: List[Dict[str, Any]] = []
    try:
        flatten(ctx)
        wanted = {w.strip().upper() for w in args.only.split(",") if w.strip()}
        for name, fn in (SCENARIOS_NET if is_netting(inst) else SCENARIOS_HEDGE):
            if wanted and name.split()[0].upper() not in wanted:
                continue
            results.append(run(name, fn, ctx))
    finally:
        flatten(ctx)
        for e in created:
            try:
                c.unfollow_master(e, MASTER_ID, instance=inst)
            except Exception as ex:
                print(f"[!] could not remove temporary link for {e}: {ex}")
        if created:
            print(f"[*] removed {len(created)} temporary {inst} links")
    return {"instance": inst, "mode": mode_name(inst), "followers": len(emails), "note": note, "results": results}


def write_reports(blocks, args) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = BASE_DIR / "reports" / "evidence"; out.mkdir(parents=True, exist_ok=True)
    (out / f"netting_hedging_evidence_{ts}.json").write_text(json.dumps(
        {"suite": "Netting vs Hedging", "timestamp": datetime.now(timezone.utc).isoformat(), "symbol": args.symbol,
         "lot": args.lot, "blocks": blocks}, indent=2, default=str), encoding="utf-8")
    L = ["# Netting vs Hedging Evidence Report", "", f"**Generated:** {datetime.now(timezone.utc).isoformat()}  ",
         f"**Symbol:** `{args.symbol}` | **Lot:** {args.lot} | **Master:** `{args.master}`", ""]
    for b in blocks:
        L += [f"## {b['instance']} ({b['mode']}) - {b['followers']} followers", f"_{b['note']}_", "",
              "| Scenario | Result | Detail |", "| :--- | :---: | :--- |"]
        for r in b["results"]:
            icon = "✅" if r["status"] == "PASS" else "❌"
            detail = "; ".join(r["failures"]) if r["failures"] else "; ".join(r["notes"][:3])
            L.append(f"| {r['name']} | {icon} {r['status']} | {detail.replace('|', '/')} |")
        L.append("")
    p = out / f"netting_hedging_evidence_{ts}.md"
    p.write_text("\n".join(L) + "\n", encoding="utf-8")
    return p


def main() -> int:
    ap = argparse.ArgumentParser(description="Netting vs Hedging suite")
    ap.add_argument("--instances", default="paper,paper-net", help="comma list of: " + ", ".join(INSTANCES))
    ap.add_argument("--followers", type=int, default=10, help="how many followers (1..N) to verify per instance")
    ap.add_argument("--end", type=int, default=None, help="alias for --followers (dashboard compatibility)")
    ap.add_argument("--start", type=int, default=1, help="ignored; followers always start at 1")
    ap.add_argument("--instance", default=None, help="single instance (dashboard compatibility)")
    ap.add_argument("--symbol", default="BINANCE:ETHUSDT.P")
    ap.add_argument("--lot", type=float, default=0.1)
    ap.add_argument("--master", default=MASTER_EMAIL)
    ap.add_argument("--allow-a-book", action="store_true")
    ap.add_argument("--only", default="", help="comma list of scenario ids, e.g. N5,P1")
    args = ap.parse_args()
    if args.end:
        args.followers = min(args.followers if args.followers != 10 else args.end, args.end)
    insts = [args.instance] if args.instance else [i.strip() for i in args.instances.split(",") if i.strip()]
    bad = [i for i in insts if i not in INSTANCES]
    if bad:
        print(f"[ABORT] unknown instance(s): {bad}"); return 2

    c = BlackTraderClient(BASE_URL)
    blocks = [run_instance(c, i, args) for i in insts]
    mp = write_reports(blocks, args)
    total = sum(len(b["results"]) for b in blocks)
    failed = sum(1 for b in blocks for r in b["results"] if r["status"] != "PASS")
    print("\n" + "=" * 80)
    for b in blocks:
        p = sum(1 for r in b["results"] if r["status"] == "PASS")
        print(f" {b['instance']:10s} {b['mode']:8s} {p}/{len(b['results'])} passed  ({b['followers']} followers)")
    print(f" SUMMARY: {total - failed}/{total} passed\n Report : {mp}")
    print("=" * 80)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
