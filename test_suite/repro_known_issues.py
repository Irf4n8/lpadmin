#!/usr/bin/env python3
"""Reproduces the confirmed defects with the exact requests (staging, real/hedging). Prints request -> response for each."""
import sys, time, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import test_suite.go_live_spec_runner as g
from test_suite.go_live_spec_runner import *  # noqa


def main():
    g.MID = c.get_copy_followers(M, I)[0]["master_client_id"]
    OUT = {}

    def show(tag, req, status, body):
        print(f"   {req}\n   -> HTTP {status} {str(body)[:230]}", flush=True)

    print("== D1  multiplier 0 is silently stored as 1x (C007)")
    f = F[1]
    r = c.oms(f, "POST", "/copy/follow", I, json={"master_client_id": g.MID, "method": "multiplier", "multiplier": 0, "reverse": False, "copy_mode": "public"})
    show("D1", f"POST /v1/oms/real/copy/follow as follower2  body multiplier=0", r["status_code"], {k: r["data"]["follow"][k] for k in ("method", "multiplier")} if r["status_code"] == 200 else r["data"])
    OUT["D1"] = {"status": r["status_code"], "stored_multiplier": r["data"]["follow"]["multiplier"] if r["status_code"] == 200 else None}
    r = c.oms(f, "POST", "/copy/follow", I, json={"master_client_id": g.MID, "method": "multiplier", "multiplier": -1})
    show("D1b", "same call with multiplier=-1 (correctly rejected)", r["status_code"], r["data"])
    follow(f)

    print("\n== D2  order below the minimum size is accepted (N005)")
    clean(F)
    r = buy(0.0001)
    oid = oid_of(r); time.sleep(4)
    mo = [o for o in orders(M) if o.get("order_id") == oid]
    show("D2", "POST /v1/oms/real/orders  {symbol BINANCE:BTCUSDT.P, side BUY, type MARKET, qty 0.0001}", r["status_code"], {k: mo[0].get(k) for k in ("state", "requested_qty", "filled_qty")} if mo else r["data"])
    print(f"   follower1 copy: {[(o['state'], o['requested_qty']) for o in orders(F[0]) if (o.get('copy_ref') or '').lstrip('-') == oid]}")
    OUT["D2"] = {"status": r["status_code"], "order": mo[:1]}
    clean(F)

    print("\n== D3  STOP edit: 'price' stays old, 'trigger_price' moves")
    buy(); time.sleep(3); p = pos(M); lp = p[0]["current_price"]; clean(F)
    p1 = round(lp + 500, 1); p2 = round(p1 + 100, 1)
    r = buy(order_type="STOP", price=p1); oid = oid_of(r); time.sleep(3)
    rr = c.oms(M, "PUT", f"/orders/{oid}/modify", I, json={"trigger_price": p2}); time.sleep(3)
    mo = [o for o in orders(M) if o.get("order_id") == oid][0]
    show("D3", f"STOP placed at {p1}; PUT /v1/oms/real/orders/<id>/modify {{\"trigger_price\": {p2}}}", rr["status_code"], {k: mo.get(k) for k in ("type", "price", "trigger_price")})
    OUT["D3"] = {k: mo.get(k) for k in ("price", "trigger_price")}
    clean(F)

    print("\n== D4  unfollow + follow again keeps old orders/trades/P&L (#4)")
    f = F[2]
    buy(0.01); wait(lambda: pos(f)); clean(F); time.sleep(3)
    b = (len(hist(f)), len(orders(f)), round(sum(h["realized_pnl"] for h in hist(f)), 4))
    u = c.unfollow_master(f, g.MID, I); time.sleep(2); fo = follow(f); time.sleep(3)
    a = (len(hist(f)), len(orders(f)), round(sum(h["realized_pnl"] for h in hist(f)), 4))
    show("D4", f"POST /copy/unfollow then POST /copy/follow as follower3; before (history rows, orders, realized P&L) {b}", fo["status_code"], f"after re-follow {a}")
    OUT["D4"] = {"before": b, "after": a}
    print("\nDONE quick repros")
    json.dump(OUT, open(ROOT / "reports" / "evidence" / "repro_known_issues.json", "w"), indent=2, default=str)


if __name__ == "__main__":
    main()
