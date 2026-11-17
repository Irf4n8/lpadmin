#!/usr/bin/env python3
"""
Order-count parity test: master vs followers at volume (200+ orders)
====================================================================
The master places N small MARKET orders (alternating BUY / SELL, a few in parallel).  After the fan-out settles
the runner counts, for the master and for every follower, the entry orders created since the test started
(squareoff / protection orders are excluded) and compares them with what the master placed.

It reports, per follower: orders received, filled, rejected, and open positions, and flags every follower whose
count does not equal the master's.  It works on hedging (`real`) and netting (`real-net`); on netting the
position count is expected to be 1 (or 0) while the ORDER count must still match.

Safety: staging only. Uses the real-money instance, so it needs --i-understand-real-money.  Accounts are flattened
at the start and at the end.  Qty is tiny (default 0.001).

Usage:
    python test_suite/order_count_parity_runner.py --instance real     --orders 200 --i-understand-real-money
    python test_suite/order_count_parity_runner.py --instance real-net --orders 200 --i-understand-real-money
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import BASE_URL, DEFAULT_DOMAIN, DEFAULT_PREFIX, FOLLOWER_COUNT, MASTER_EMAIL  # noqa: E402
from test_suite.client import BlackTraderClient  # noqa: E402

EXCLUDED_SOURCES = {"squareoff", "algo_protection", "reduce"}


def entry_orders(orders, since_iso):
    """Entry orders created at/after `since_iso` (ISO strings compare chronologically)."""
    out = []
    for o in orders or []:
        if (o.get("created_at") or "") < since_iso:
            continue
        if o.get("source") in EXCLUDED_SOURCES or o.get("type") in ("TP", "SL"):
            continue
        out.append(o)
    return out


def summarize(orders):
    s = {"total": len(orders), "filled": 0, "rejected": 0, "cancelled": 0, "other": 0}
    for o in orders:
        st = (o.get("state") or "").upper()
        key = {"FILLED": "filled", "REJECTED": "rejected", "CANCELLED": "cancelled"}.get(st, "other")
        s[key] += 1
    return s


def snapshot(c, emails, instance, since_iso):
    def one(e):
        try:
            d = c.get_orders(e, instance)
            ents = entry_orders(d.get("orders"), since_iso)
            return e, summarize(ents), len(d.get("orders") or []), ents
        except Exception as ex:
            return e, {"error": str(ex)[:80]}, 0, []
    with ThreadPoolExecutor(max_workers=10) as ex:
        return {e: (s, n, ents) for e, s, n, ents in ex.map(one, emails)}


def main():
    ap = argparse.ArgumentParser(description="Master vs follower order-count parity at volume")
    ap.add_argument("--master", default=MASTER_EMAIL)
    ap.add_argument("--prefix", default=DEFAULT_PREFIX)
    ap.add_argument("--domain", default=DEFAULT_DOMAIN)
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int, default=FOLLOWER_COUNT)
    ap.add_argument("--instance", choices=["real", "real-net"], default="real")
    ap.add_argument("--orders", type=int, default=200)
    ap.add_argument("--qty", type=float, default=0.001)
    ap.add_argument("--delay", type=float, default=0.0, help="seconds to wait after each master order (slow mode)")
    ap.add_argument("--multiplier", type=float, default=1.0, help="followers' multiplier, used to check the net position size")
    ap.add_argument("--pattern", choices=["alternate", "blocks", "buy", "sell"], default="alternate",
                    help="alternate = BUY,SELL,BUY,SELL...   blocks = all BUYs first, then all SELLs   buy / sell = one side only")
    ap.add_argument("--symbol", default="BINANCE:BTCUSDT.P")
    ap.add_argument("--threads", type=int, default=4, help="parallel order placers on the master")
    ap.add_argument("--max-wait", type=int, default=240, help="seconds to wait for the fan-out to settle")
    ap.add_argument("--i-understand-real-money", action="store_true")
    a = ap.parse_args()
    if not a.i_understand_real_money:
        sys.exit("Refusing: this places real-instance orders. Add --i-understand-real-money")

    c = BlackTraderClient(BASE_URL, max_workers=10)
    followers = [f"{a.prefix}{i}@{a.domain}" for i in range(a.start, a.end + 1)]
    everyone = [a.master] + followers
    inst = a.instance
    print(f"[*] pattern: {a.pattern}")
    print(f"[*] {inst}: master {a.master} + {len(followers)} followers, {a.orders} orders x {a.qty} {a.symbol}")

    print("[*] flatten before ...")
    c.teardown_all_accounts(a.master, followers, instance=inst)
    time.sleep(2)

    since = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    time.sleep(0.5)

    def fire(i):
        if a.pattern in ("buy", "sell"):
            side = a.pattern.upper()
        elif a.pattern == "alternate":
            side = "BUY" if i % 2 == 0 else "SELL"
        else:
            side = "BUY" if i < a.orders // 2 else "SELL"
        r = c.place_order(a.master, symbol=a.symbol, side=side, qty=a.qty, instance=inst)
        if a.delay:
            time.sleep(a.delay)
        return i, r.get("status_code"), (r.get("data") or {}).get("order", {}).get("order_id") if isinstance(r.get("data"), dict) else None, \
            (str(r.get("data"))[:100] if r.get("status_code") != 200 else "")
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=a.threads) as ex:
        placed = list(ex.map(fire, range(a.orders)))
    dur = time.time() - t0
    ok = [p for p in placed if p[1] == 200]
    bad = [p for p in placed if p[1] != 200]
    print(f"[+] master accepted {len(ok)}/{a.orders} orders in {dur:.1f}s ({len(bad)} refused)")
    if bad:
        print("    first refusals:", [p[3] for p in bad[:3]])

    print("[*] waiting for the fan-out to settle ...")
    last, stable, waited = None, 0, 0
    snap = {}
    while waited < a.max_wait:
        time.sleep(8)
        waited += 8
        snap = snapshot(c, everyone, inst, since)
        counts = tuple(sorted(v[0].get("total", -1) for v in snap.values()))
        stable = stable + 1 if counts == last else 0
        last = counts
        m = snap[a.master][0].get("total")
        f_tot = [snap[e][0].get("total", 0) for e in followers]
        print(f"    t+{waited:3d}s master={m}  followers min/max={min(f_tot)}/{max(f_tot)}")
        if stable >= 2:
            break

    master = snap[a.master][0]
    master_ids = {o.get("order_id") for o in snap[a.master][2]}
    mism, missing_by = [], {}
    for e in followers:
        s = snap[e][0]
        refs = {(o.get("copy_ref") or "").lstrip("-") for o in snap[e][2]}
        miss = sorted(master_ids - refs)
        if miss:
            missing_by[e] = miss
        if s.get("total") != master.get("total") or s.get("filled") != master.get("filled") or miss:
            mism.append((e, dict(s, missing_master_orders=len(miss))))
    dist = {}
    for miss in missing_by.values():
        for oid in miss:
            dist[oid] = dist.get(oid, 0) + 1
    pos, netq = {}, {}
    for e in everyone:
        d = c.get_positions(e, inst)
        plist = d.get("positions") or []
        pos[e] = len(plist)
        netq[e] = round(sum((float(p.get("net_qty") or 0)) * (1 if p.get("side") == "BUY" else -1) for p in plist), 8)
    exp_q = round(netq[a.master] * a.multiplier, 8)
    qty_bad = [(e, netq[e]) for e in followers if abs(netq[e] - exp_q) > 1e-9]
    cap_hint = sorted({snap[e][1] for e in everyone})
    mq = {o.get("order_id"): float(o.get("filled_qty") or 0) for o in snap[a.master][2]}
    ratios = {}
    for e in followers[:20]:
        for o in snap[e][2]:
            ref = (o.get("copy_ref") or "").lstrip("-")
            if ref in mq and mq[ref]:
                r_ = round(float(o.get("filled_qty") or 0) / mq[ref], 4)
                ratios[r_] = ratios.get(r_, 0) + 1

    print("\n" + "=" * 78)
    print(f" INSTANCE {inst}   orders placed by master: {len(ok)} / {a.orders}")
    print(f" MASTER   entry orders {master}  open positions: {pos[a.master]}")
    ftot = [snap[e][0].get("total", 0) for e in followers]
    print(f" FOLLOWERS ({len(followers)}): orders per follower min={min(ftot)} max={max(ftot)}  "
          f"match master: {len(followers) - len(mism)}/{len(followers)}")
    print(f" positions per follower: min={min(pos[e] for e in followers)} max={max(pos[e] for e in followers)}")
    print(f" raw order-list length per account (API cap hint): {cap_hint[:6]}")
    print(f" NET POSITION qty: master {netq[a.master]:g} -> expected per follower {exp_q:g} (x{a.multiplier:g}); "
          f"followers off: {len(qty_bad)}/{len(followers)}  e.g. {sorted({q for _, q in qty_bad})[:6]}")
    print(f" size ratio follower/master per copied order (first 20 followers): {dict(sorted(ratios.items()))}")
    for e, s in mism[:10]:
        print(f"   MISMATCH {e.split('@')[0]}: {s}")
    if dist:
        worst = sorted(dist.items(), key=lambda x: -x[1])[:5]
        print(f" master orders missing on followers (order id -> followers missing it): {worst}")
        print(f" distinct master orders missing anywhere: {len(dist)} of {len(master_ids)}")
    verdict = "PASS" if not mism and not qty_bad and len(ok) == a.orders else "FAIL"
    print(f" RESULT: {verdict}")
    print("=" * 78)

    out = Path(__file__).resolve().parent.parent / "reports" / "evidence"
    out.mkdir(parents=True, exist_ok=True)
    f = out / f"order_parity_{inst}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    f.write_text(json.dumps({
        "instance": inst, "pattern": a.pattern, "orders_requested": a.orders, "orders_accepted": len(ok), "refused": [p[3] for p in bad[:20]],
        "master": master, "master_positions": pos[a.master], "followers": len(followers),
        "mismatches": [{"email": e, "summary": s} for e, s in mism], "api_list_lengths": cap_hint,
        "follower_order_totals": ftot, "missing_master_orders_by_follower": {k.split("@")[0]: v for k, v in list(missing_by.items())[:20]}, "missing_order_distribution": dist, "size_ratios": {str(k): v for k, v in ratios.items()}, "verdict": verdict, "duration_place_sec": round(dur, 1)}, indent=2))
    print(f"[*] evidence: {f}")

    print("[*] flatten after ...")
    c.teardown_all_accounts(a.master, followers, instance=inst)
    sys.exit(0 if verdict == "PASS" else 1)


if __name__ == "__main__":
    main()
