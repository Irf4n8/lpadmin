#!/usr/bin/env python3
"""
Client-reported issues, tested against staging (real / hedging instance, tiny sizes)
===================================================================================
Cohort: master + followers 1..N (default 5) at multiplier 2.  Every test prints its observation and a verdict
(PASS / FAIL / BLOCKED / NOT-TESTABLE); evidence is written to reports/evidence/client_issues_<ts>.json.

  T2  partial close      reduce a master position -> follower count / lot / realized P&L vs master x multiplier
  T3  pending edit       edit the trigger price of a LIMIT order; master + follower pending orders must follow
  T4  re-follow history   unfollow + follow the same master -> follower's old orders/trades/P&L still shown?
  T5  STOP multiplier    STOP pending copied to followers at master qty x multiplier
  T7  history split      master and follower history are separate lists
  T13 independent bulk   follower bulk close does not touch the master; master bulk close closes followers
  T9  bulk close 200+    (--bulk 210) master opens N orders, one bulk close, count what stays open
Not testable through the API: #11 (CRM B-book -> A-book), #6 / #12 (withdrawal square-off), #8 / #10 (PAMM / MAM, need
those module accounts) - reported as NOT-TESTABLE with the reason.
"""
import argparse, json, sys, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import BASE_URL, DEFAULT_DOMAIN, DEFAULT_PREFIX, MASTER_EMAIL  # noqa: E402
from test_suite.client import BlackTraderClient  # noqa: E402

INST = "real"
SYM = "BINANCE:BTCUSDT.P"
RES = []


def rec(tid, name, verdict, detail):
    RES.append({"id": tid, "name": name, "verdict": verdict, "detail": detail})
    print(f"\n[{tid}] {name}: {verdict}\n     {detail}")


def wait(cond, timeout=30, step=1.5):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = cond()
        if v:
            return v
        time.sleep(step)
    return cond()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--followers", type=int, default=5)
    ap.add_argument("--mult", type=float, default=2.0)
    ap.add_argument("--qty", type=float, default=0.01)
    ap.add_argument("--only", default="", help="comma list e.g. T2,T3")
    ap.add_argument("--bulk", type=int, default=0, help="T9: number of master orders (e.g. 210); uses 100 followers")
    ap.add_argument("--i-understand-real-money", action="store_true")
    a = ap.parse_args()
    if not a.i_understand_real_money:
        sys.exit("Refusing: real-instance orders. Add --i-understand-real-money")
    only = {s.strip().upper() for s in a.only.split(",") if s.strip()}
    run = lambda t: not only or t in only  # noqa: E731

    c = BlackTraderClient(BASE_URL, max_workers=10)
    M = MASTER_EMAIL
    n = 100 if a.bulk else a.followers
    F = [f"{DEFAULT_PREFIX}{i}@{DEFAULT_DOMAIN}" for i in range(1, n + 1)]
    mid = c.get_copy_followers(M, INST)[0]["master_client_id"]
    clean = lambda: c.teardown_all_accounts(M, F, instance=INST)  # noqa: E731

    print(f"[*] relink followers 1..{n} to master on {INST} at x{a.mult}")
    for f in F:
        r = c.follow_master(f, mid, INST, "multiplier", a.mult)
        if r["status_code"] != 200:
            print("   follow failed", f, r["data"])
    clean(); time.sleep(2)

    def pos(e): return c.get_positions(e, INST).get("positions") or []
    def orders(e): return c.get_orders(e, INST).get("orders") or []
    def hist(e): return c.get_history(e, INST).get("history") or []

    # ---------------- T2 partial close ----------------
    if run("T2"):
        clean(); t0 = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
        for _ in range(3):
            c.place_order(M, qty=a.qty, side="BUY", instance=INST); time.sleep(0.5)
        wait(lambda: all(len(pos(f)) == 3 for f in F))
        mp = pos(M)
        bad = []
        mp[0] and c.reduce_position(M, mp[0]["market_order_id"], a.qty / 2, INST)
        time.sleep(6)
        mq = round(sum(p["net_qty"] for p in pos(M)), 8)
        mh = [h for h in hist(M) if h["executed_at"] >= t0 and h.get("exit_source") == "reduce"]
        mpnl = sum(h["realized_pnl"] for h in mh)
        for f in F:
            fq = round(sum(p["net_qty"] for p in pos(f)), 8)
            fh = [h for h in hist(f) if h["executed_at"] >= t0 and h.get("exit_source") in ("reduce", "copy_close", "copy_reduce")]
            fpnl = sum(h["realized_pnl"] for h in fh)
            fcnt = len(pos(f))
            ok_q = abs(fq - mq * a.mult) < 1e-9
            ok_c = fcnt == len(pos(M))
            ok_p = abs(fpnl - mpnl * a.mult) <= max(0.02, abs(mpnl * a.mult) * 0.15)
            if not (ok_q and ok_c and ok_p):
                bad.append(f"{f.split('@')[0]}: qty {fq} (want {mq*a.mult}), positions {fcnt} (want {len(pos(M))}), reduce-pnl {fpnl:.4f} (want ~{mpnl*a.mult:.4f})")
        rec("T2", "partial close: count / lot / P&L", "PASS" if not bad else "FAIL",
            f"master open qty {mq}, positions {len(pos(M))}, reduce pnl {mpnl:.4f}; followers off: {len(bad)}/{len(F)} {bad[:3]}")
        clean()

    # ---------------- T3 pending edit (LIMIT and STOP) ----------------
    if run("T3"):
        for kind, side, off in (("LIMIT", "BUY", -400), ("STOP", "BUY", 500)):
            clean()
            c.place_order(M, qty=a.qty, instance=INST); time.sleep(3)
            p = pos(M); lp = p[0]["current_price"] if p else None; clean(); time.sleep(2)
            tid = f"T3-{kind}"
            if lp is None:
                rec(tid, f"edit {kind} price", "BLOCKED", "no live price (master order refused)"); continue
            p1 = round(lp + off, 1); p2 = round(p1 + (-100 if kind == "LIMIT" else 100), 1)
            r = c.place_order(M, qty=a.qty, side=side, order_type=kind, price=p1, instance=INST)
            oid = (r["data"].get("order") or {}).get("order_id") if isinstance(r["data"], dict) else None
            if not oid:
                rec(tid, f"edit {kind} price", "BLOCKED", f"order refused: {str(r['data'])[:160]}"); continue
            time.sleep(4)
            pend = lambda e: [o for o in orders(e) if o.get("state") == "PENDING" and o.get("type") == kind]  # noqa: E731
            fld = "price" if kind == "LIMIT" else "trigger_price"
            before = [sorted({o.get(fld) for o in pend(f)}) for f in F]
            note = ""
            if kind == "STOP":   # the obvious `price` field: does the API accept it silently?
                r0 = c.oms(M, "PUT", f"/orders/{oid}/modify", INST, json={"price": p2}); time.sleep(3)
                m0 = [o for o in orders(M) if o.get("order_id") == oid]
                note = f"[sending only 'price' -> HTTP {r0['status_code']}, trigger_price now {m0[0].get('trigger_price') if m0 else None}, price field {m0[0].get('price') if m0 else None} (the 'price' field is NOT updated on a STOP, only trigger_price)] "
            rr = c.oms(M, "PUT", f"/orders/{oid}/modify", INST, json={fld: p2})
            time.sleep(5)
            mo = [o for o in orders(M) if o.get("order_id") == oid]
            mprice = mo[0].get(fld) if mo else None
            after = [sorted({o.get(fld) for o in pend(f)}) for f in F]
            nfq = [sorted({o.get("requested_qty") for o in pend(f)}) for f in F]
            bad = [f.split("@")[0] for f, pr in zip(F, after) if pr != [p2]]
            rec(tid, f"edit {kind} trigger price", "PASS" if rr["status_code"] == 200 and mprice == p2 and not bad else "FAIL",
                f"{note}PUT /orders/<id>/modify {{{fld}}} -> HTTP {rr['status_code']}; master {p1} -> {mprice} (want {p2}); followers had a pending {kind} before: "
                f"{sum(1 for x in before if x == [p1])}/{len(F)}; followers now at {p2}: {len(F) - len(bad)}/{len(F)} (off: {bad[:3]}); follower qty {nfq[0]}")
            clean()

    # ---------------- T5 STOP multiplier ----------------
    if run("T5"):
        clean()
        r = c.place_order(M, qty=a.qty, instance=INST); time.sleep(3)
        p = pos(M); lp = p[0]["current_price"] if p else None; clean(); time.sleep(2)
        if lp is None:
            rec("T5", "STOP multiplier", "BLOCKED", "no live price")
        else:
            trig = round(lp + 500, 1)
            r = c.place_order(M, qty=a.qty, side="BUY", order_type="STOP", price=trig, instance=INST)
            if r["status_code"] != 200:
                rec("T5", "STOP multiplier", "BLOCKED", f"stop refused: {str(r['data'])[:160]}")
            else:
                time.sleep(5)
                got = {}
                for f in F:
                    got[f.split("@")[0]] = [(o.get("type"), o.get("requested_qty"), o.get("trigger_price")) for o in orders(f) if o.get("state") == "PENDING"]
                want = round(a.qty * a.mult, 8)
                bad = [k for k, v in got.items() if not any(t == "STOP" and abs(float(q or 0) - want) < 1e-9 for t, q, _ in v)]
                rec("T5", "STOP pending copied at multiplier", "PASS" if not bad else "FAIL",
                    f"master STOP qty {a.qty}, want follower qty {want}; followers without matching STOP: {len(bad)}/{len(F)}; sample {list(got.items())[:2]}")
        clean()

    # ---------------- T4 re-follow history ----------------
    if run("T4"):
        clean()
        f = F[0]
        c.place_order(M, qty=a.qty, instance=INST); time.sleep(4); clean(); time.sleep(3)
        before = (len(hist(f)), len(orders(f)))
        u = c.unfollow_master(f, mid, INST); time.sleep(2)
        fo = c.follow_master(f, mid, INST, "multiplier", a.mult); time.sleep(3)
        after = (len(hist(f)), len(orders(f)))
        rec("T4", "re-follow shows old history", "FAIL (old data still shown)" if after[0] and after[1] else "PASS",
            f"unfollow HTTP {u['status_code']}, follow HTTP {fo['status_code']}; follower history rows {before[0]} -> {after[0]}, orders {before[1]} -> {after[1]} "
            f"(a fresh relationship should start empty if the client expects that; this is the platform's current behaviour)")

    # ---------------- T7 history split ----------------
    if run("T7"):
        mh, fh = hist(M), hist(F[0])
        mi, fi = {h["order_id"] for h in mh}, {h["order_id"] for h in fh}
        rec("T7", "master / follower history separate", "PASS" if mh and fh and not (mi & fi) else "FAIL",
            f"master history rows {len(mh)}, follower1 rows {len(fh)}, shared order ids {len(mi & fi)}; follower rows are marked entry_source=copy: "
            f"{sum(1 for h in fh if h.get('entry_source') == 'copy')}/{len(fh)}; master rows entry_copy_kind=master: {sum(1 for h in mh if h.get('entry_copy_kind') == 'master')}/{len(mh)}")

    # ---------------- T13 independent bulk close ----------------
    if run("T13"):
        clean()
        for _ in range(4):
            c.place_order(M, qty=a.qty, instance=INST); time.sleep(0.5)
        wait(lambda: all(len(pos(f)) == 4 for f in F))
        c.bulk_squareoff(F[0], INST); time.sleep(5)
        m_after, f0_after = len(pos(M)), len(pos(F[0]))
        others = [len(pos(f)) for f in F[1:]]
        c.bulk_squareoff(M, INST); time.sleep(8)
        m2, f2 = len(pos(M)), [len(pos(f)) for f in F]
        rec("T13", "bulk close from follower and from master", "PASS" if f0_after == 0 and m_after == 4 and all(x == 4 for x in others) and m2 == 0 and not any(f2) else "FAIL",
            f"follower1 bulk close: follower1 open {f0_after}, master still {m_after} (want 4), other followers {others}; "
            f"then master bulk close: master {m2}, followers open {f2}")
        clean()

    # ---------------- T9 bulk close 200+ ----------------
    if run("T9") and a.bulk:
        clean()
        def fire(i):
            return c.place_order(M, qty=0.001, side="BUY", instance=INST)["status_code"]
        with ThreadPoolExecutor(max_workers=4) as ex:
            codes = list(ex.map(fire, range(a.bulk)))
        ok = codes.count(200)
        print(f"[*] master accepted {ok}/{a.bulk}; waiting for fan-out ...")
        last = None
        for _ in range(40):
            time.sleep(8)
            cnt = [len(pos(f)) for f in F]
            print("    followers open min/max", min(cnt), max(cnt))
            if (min(cnt), max(cnt)) == last: break
            last = (min(cnt), max(cnt))
        before_m, before_f = len(pos(M)), [len(pos(f)) for f in F]
        res = c.bulk_squareoff(M, INST)
        print("    bulk close HTTP", res["status_code"], str(res["data"])[:200])
        time.sleep(30)
        left_m, left_f = len(pos(M)), [len(pos(f)) for f in F]
        rec("T9", f"bulk close with {ok} open orders", "PASS" if left_m == 0 and not any(left_f) else "FAIL",
            f"before: master {before_m}, followers min/max {min(before_f)}/{max(before_f)}; bulk close HTTP {res['status_code']}; "
            f"after 30 s: master left {left_m}, followers left min/max {min(left_f)}/{max(left_f)}, followers not flat {sum(1 for x in left_f if x)}/{len(F)}")
        clean()

    for tid, why in (("#11", "CRM B-book -> A-book conversion is a CRM/admin action with no API we can call"),
                     ("#6/#12", "withdrawal-triggered square-off needs a real withdrawal flow, not just a balance edit"),
                     ("#8", "PAMM unfollow needs a PAMM master and a funded PAMM subscription"),
                     ("#10", "MAM pending orders need a MAM master + follower setup")):
        pass
    out = Path(__file__).resolve().parent.parent / "reports" / "evidence"
    out.mkdir(parents=True, exist_ok=True)
    f = out / f"client_issues_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    f.write_text(json.dumps(RES, indent=2, default=str))
    print("\n[*] evidence:", f)


if __name__ == "__main__":
    main()
