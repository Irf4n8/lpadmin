#!/usr/bin/env python3
"""
Market / LIMIT / STOP orders (BUY and SELL) in every copy mode: multiplier, balance, equity.
Staging, real / hedging, master + followers 1..10.  Needs --i-understand-real-money.
Per mode and per order type: place -> follower mirror (price, side, qty scaled) -> modify -> cancel -> clean.
Plus a trigger test: STOP BUY above / STOP SELL below the market, wait for one to fill, check follower fill + qty.
Evidence: reports/evidence/pending_modes_<ts>.json
"""
import sys, time, json, argparse
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import test_suite.go_live_spec_runner as g
from test_suite.go_live_spec_runner import *  # noqa


def main():
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
        print(f"  [{'PASS' if ok else 'FAIL'}] {mode:10s} {name}: {detail}", flush=True)


    def setup(mode):
        clean(FS)
        ratios = {}
        if mode == "multiplier":
            for f in FS: follow(f, "multiplier", 2.0); ratios[f] = 2.0
        else:
            g.setbal(M, BASE)
            for i, f in enumerate(FS):
                amt = BASE * (1 if i % 2 == 0 else 2); g.setbal(f, amt); ratios[f] = amt / BASE
            for f in FS: c.follow_master(f, g.MID, I, mode, 1.0)
        time.sleep(3)
        return ratios


    def mirrored(kind, side, p, q, ratios):
        fld = "price" if kind == "LIMIT" else "trigger_price"
        ok, bad = 0, []
        for f in FS:
            ps = [o for o in pend(f, kind) if o.get("side") == side and abs((o.get(fld) or 0) - p) < 0.05]
            want = q * ratios[f]
            if len(ps) == 1 and abs(ps[0]["requested_qty"] - want) < 1e-9: ok += 1
            else: bad.append((f.split("@")[0], len(ps), [o["requested_qty"] for o in ps], want))
        return ok, bad[:3]


    def run_mode(mode):
        print(f"\n=== MODE {mode} ===", flush=True)
        ratios = setup(mode)
        # market BUY / SELL
        for side in ("BUY", "SELL"):
            clean(FS); r = buy(side=side); sgn = 1 if side == "BUY" else -1
            wait(lambda: all(netq(f) != 0 for f in FS))
            okc = sum(abs(netq(f) - sgn * Q * ratios[f]) < 1e-9 for f in FS)
            rec2(mode, f"MARKET {side}", r["status_code"] == 200 and okc == len(FS), f"accepted={r['status_code']}; followers at expected scaled qty {okc}/{len(FS)}")
            clean(FS)
        lp = g.price()
        if lp is None: rec2(mode, "live price", False, "no live price"); return
        cases = [("LIMIT", "BUY", lp - 400, lp - 500), ("LIMIT", "SELL", lp + 400, lp + 500),
                 ("STOP", "BUY", lp + 400, lp + 500), ("STOP", "SELL", lp - 400, lp - 500)]
        for kind, side, p1, p2 in cases:
            p1, p2 = round(p1, 1), round(p2, 1); clean(FS)
            r = buy(side=side, order_type=kind, price=p1); oid = oid_of(r)
            if not oid:
                rec2(mode, f"{kind} {side} place", False, f"rejected HTTP {r['status_code']}: {str(r['data'])[:160]}"); continue
            time.sleep(4); ok, bad = mirrored(kind, side, p1, Q, ratios)
            rec2(mode, f"{kind} {side} place+mirror", ok == len(FS), f"@ {p1}: {ok}/{len(FS)} followers mirrored w/ scaled qty {bad if bad else ''}")
            body = {"price": p2} if kind == "LIMIT" else {"trigger_price": p2}
            rr = c.oms(M, "PUT", f"/orders/{oid}/modify", I, json=body); time.sleep(5)
            ok, bad = mirrored(kind, side, p2, Q, ratios)
            rec2(mode, f"{kind} {side} modify", rr["status_code"] == 200 and ok == len(FS), f"HTTP {rr['status_code']}; moved to {p2} on {ok}/{len(FS)} {bad if bad else ''}")
            cr = c.cancel_order(M, oid, I); time.sleep(5)
            left = sum(len(pend(f)) for f in FS)
            rec2(mode, f"{kind} {side} cancel", cr["status_code"] == 200 and left == 0, f"HTTP {cr['status_code']}; follower pendings left {left}")
        # trigger test
        clean(FS); lp = g.price() or lp
        up = oid_of(buy(side="BUY", order_type="STOP", price=round(lp + 20, 1))); dn = oid_of(buy(side="SELL", order_type="STOP", price=round(lp - 20, 1)))
        t0 = time.time(); side = None
        while time.time() - t0 < A.trigger_wait:
            if pos(M): side = pos(M)[0]["side"]; break
            time.sleep(2)
        if not side:
            rec2(mode, "STOP trigger", False, f"neither STOP (+/-20 around {lp}) triggered within {A.trigger_wait}s (inconclusive)")
        else:
            sgn = 1 if side == "BUY" else -1; time.sleep(4)
            okc = sum(abs(netq(f) - sgn * Q * ratios[f]) < 1e-9 for f in FS)
            rec2(mode, f"STOP {side} trigger->fill", okc == len(FS), f"master filled {side}; followers filled at scaled qty {okc}/{len(FS)}")
        for o in (up, dn):
            if o: c.cancel_order(M, o, I)
        clean(FS)


    for mode in A.modes.split(","): run_mode(mode.strip())
    clean(FS)
    for f in FS: follow(f, "multiplier", 2.0)
    n_ok = sum(r["ok"] for r in RESULTS)
    print(f"\nSUMMARY {n_ok}/{len(RESULTS)} passed")
    out = ROOT / "reports" / "evidence" / f"pending_modes_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(RESULTS, indent=1)); print("evidence:", out)


if __name__ == "__main__":
    main()
