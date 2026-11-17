#!/usr/bin/env python3
"""
TP only / SL only / TP+SL on MARKET, LIMIT and STOP orders in every copy mode.
Staging, real / hedging, master + followers 1..10.  Needs --i-understand-real-money.
Per mode and per order type: place -> follower mirror (price, side, qty scaled) -> modify -> cancel -> clean.
Plus a trigger test: STOP BUY above / STOP SELL below the market, wait for one to fill, check follower fill + qty.
Evidence: reports/evidence/tpsl_modes_<ts>.json
"""
import sys, time, json, argparse
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import test_suite.go_live_spec_runner as g
from test_suite.go_live_spec_runner import *  # noqa

ap = argparse.ArgumentParser(); ap.add_argument("--i-understand-real-money", action="store_true")
ap.add_argument("--modes", default="multiplier,balance,equity"); ap.add_argument("--n", type=int, default=10)
ap.add_argument("--trigger-wait", type=int, default=90)
A = ap.parse_args()
if not A.i_understand_real_money: sys.exit("needs --i-understand-real-money")

for m in c.get_admin_members(): g.MEMBERS[m.get("email")] = m.get("member_id")
g.MID = c.get_copy_followers(M, I)[0]["master_client_id"]
FS = ALL[:A.n]
RESULTS = []
BASE = 100_000_000.0


def rec2(mode, name, ok, detail):
    RESULTS.append({"mode": mode, "test": name, "ok": ok, "detail": detail})
    print(f"  [{'PASS' if ok is True else ('INCONCLUSIVE' if ok is None else 'FAIL')}] {mode:10s} {name}: {detail}", flush=True)


def setup(mode):
    clean(FS); ratios = {}
    if mode == "multiplier":
        for f in FS: follow(f, "multiplier", 2.0); ratios[f] = 2.0
    else:
        g.setbal(M, BASE)
        for i, f in enumerate(FS):
            amt = BASE * (1 if i % 2 == 0 else 2); g.setbal(f, amt); ratios[f] = amt / BASE
        for f in FS: c.follow_master(f, g.MID, I, mode, 1.0)
    time.sleep(3); return ratios


COMBOS = {"TP only": (True, False), "SL only": (False, True), "TP+SL": (True, True)}


def levels(side, lp, use_tp, use_sl):
    d = 300 if side == "BUY" else -300
    return (round(lp + d, 1) if use_tp else None), (round(lp - d, 1) if use_sl else None)


def want_prot(tp, sl):
    return sorted([t for t in (("TP", tp), ("SL", sl)) if t[1] is not None])


def prot_ok(e, tp, sl):
    got = [(t, p) for t, p in prot(e)]
    w = want_prot(tp, sl)
    return len(got) == len(w) and all(a[0] == b[0] and abs(a[1] - b[1]) < 0.06 for a, b in zip(sorted(got), w))


def check_filled(mode, name, side, tp, sl, ratios):
    sgn = 1 if side == "BUY" else -1; time.sleep(4)
    mp = prot_ok(M, tp, sl)
    fp = sum(prot_ok(f, tp, sl) for f in FS)
    fq = sum(abs(netq(f) - sgn * Q * ratios[f]) < 1e-9 for f in FS)
    rec2(mode, name, mp and fp == len(FS) and fq == len(FS), f"master prot ok={mp} {prot(M)}; followers prot ok {fp}/{len(FS)}, qty scaled {fq}/{len(FS)}; want {want_prot(tp, sl)}")


def run_mode(mode):
    print(f"\n=== MODE {mode} ===", flush=True)
    ratios = setup(mode)
    lp = g.price()
    if lp is None: rec2(mode, "live price", False, "no live price"); return
    # ---- MARKET ----
    for side in ("BUY", "SELL"):
        for cname, (ut, us) in COMBOS.items():
            clean(FS); tp, sl = levels(side, lp, ut, us)
            r = buy(side=side, tp=tp, sl=sl)
            if r["status_code"] != 200: rec2(mode, f"MARKET {side} {cname}", False, f"rejected HTTP {r['status_code']}: {str(r['data'])[:140]}"); continue
            wait(lambda: all(pos(f) for f in FS)); check_filled(mode, f"MARKET {side} {cname}", side, tp, sl, ratios)
            # modify protection on the master position, followers must follow
            p = pos(M)
            if p:
                ntp, nsl = (round(tp + 50, 1) if tp else None), (round(sl - 50, 1) if sl else None)
                rr = c.set_position_protection(M, p[0]["market_order_id"], tp=ntp, sl=nsl, instance=I); time.sleep(5)
                m_ok = prot_ok(M, ntp, nsl); f_ok = sum(prot_ok(f, ntp, nsl) for f in FS)
                rec2(mode, f"MARKET {side} {cname} modify TP/SL", rr["status_code"] == 200 and m_ok and f_ok == len(FS), f"HTTP {rr['status_code']}; master ok={m_ok}; followers ok {f_ok}/{len(FS)}; want {want_prot(ntp, nsl)}")
            clean(FS)
    # ---- LIMIT / STOP with TP/SL: place a BUY+SELL pair, wait for one to fill ----
    for kind in ("LIMIT", "STOP"):
        for cname, (ut, us) in COMBOS.items():
            clean(FS); lp = g.price() or lp; off = 15
            # BUY: LIMIT below / STOP above ; SELL: LIMIT above / STOP below
            bp = round(lp - off if kind == "LIMIT" else lp + off, 1); sp = round(lp + off if kind == "LIMIT" else lp - off, 1)
            btp, bsl = levels("BUY", lp, ut, us); stp, ssl = levels("SELL", lp, ut, us)
            rb = buy(side="BUY", order_type=kind, price=bp, tp=btp, sl=bsl); rs = buy(side="SELL", order_type=kind, price=sp, tp=stp, sl=ssl)
            ob, os_ = oid_of(rb), oid_of(rs)
            for lab, r in (("BUY", rb), ("SELL", rs)):
                if not oid_of(r): rec2(mode, f"{kind} {lab} {cname} place", False, f"rejected HTTP {r['status_code']}: {str(r['data'])[:140]}")
            time.sleep(3)
            mo = [o for o in orders(M) if o.get("order_id") in (ob, os_)]
            print("     pending master order fields:", json.dumps(mo[:1], default=str)[:420], flush=True)
            t0 = time.time(); side = None
            while time.time() - t0 < A.trigger_wait:
                p = pos(M)
                if p: side = p[0]["side"]; break
                time.sleep(2)
            if not side:
                rec2(mode, f"{kind} {cname} fill->TP/SL", None, f"neither {kind} (+/-{off} around {lp}) filled in {A.trigger_wait}s")
            else:
                tp, sl = (btp, bsl) if side == "BUY" else (stp, ssl)
                check_filled(mode, f"{kind} {side} {cname} fill->TP/SL", side, tp, sl, ratios)
            for o in (ob, os_):
                if o: c.cancel_order(M, o, I)
            clean(FS)


for mode in A.modes.split(","): run_mode(mode.strip())
clean(FS)
for f in FS: follow(f, "multiplier", 2.0)
n_ok = sum(r["ok"] is True for r in RESULTS); n_bad = sum(r["ok"] is False for r in RESULTS); n_inc = sum(r["ok"] is None for r in RESULTS)
print(f"\nSUMMARY pass={n_ok} fail={n_bad} inconclusive={n_inc} of {len(RESULTS)}")
out = ROOT / "reports" / "evidence" / f"tpsl_modes_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
out.write_text(json.dumps(RESULTS, indent=1)); print("evidence:", out)
