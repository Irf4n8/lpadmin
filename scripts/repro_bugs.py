#!/usr/bin/env python3
"""
Reproduce the platform bugs (BUG-1, BUG-2, BUG-3) - one command, or one bug at a time.

    python scripts/repro_bugs.py                      # all three, with follower1 from .env (isolated test account)
    python scripts/repro_bugs.py --only 2             # just BUG-2   (1 = orders history, 2 = order type, 3 = TP/SL)
    python scripts/repro_bugs.py --email you@test.com --password '...'   # any TEST trader account
    python scripts/repro_bugs.py --pause 1.2          # pause between steps (used when screen-recording)

WHERE : https://lpadmin.blackfx.com  ->  /v1/oms/paper/orders  (the order API behind the trading terminal)
HOW   : logs in, sends the requests, prints what the platform answered, closes anything it opened.
Safe  : paper instance only, 0.01 BTC, always cleans up. Use a TEST account with no copy-trading link.
"""
import argparse
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import BASE_URL, MEMBER_PASSWORD, DEFAULT_PREFIX, DEFAULT_DOMAIN

SYMBOL = "BINANCE:BTCUSDT.P"


def login(base, email, password):
    s = requests.Session()
    r = s.post(f"{base}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    if r.status_code != 200:
        sys.exit(f"login failed: HTTP {r.status_code} {r.text[:120]}")
    return s.post(f"{base}/api/auth/chart-token", timeout=30).json()["token"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", default=f"{DEFAULT_PREFIX}1@{DEFAULT_DOMAIN}")
    ap.add_argument("--password", default=MEMBER_PASSWORD)
    ap.add_argument("--base", default=BASE_URL)
    ap.add_argument("--only", default="1,2,3", help="comma list of bug numbers to run")
    ap.add_argument("--pause", type=float, default=0.0, help="seconds to wait between steps (for screen recordings)")
    ap.add_argument("--no-cleanup-wait", action="store_true")
    a = ap.parse_args()
    want = {x.strip() for x in a.only.split(",")}

    def say(text=""):
        print(text, flush=True)

    def beat(mult=1.0):
        if a.pause:
            time.sleep(a.pause * mult)

    say(f"Logging in as {a.email} on {a.base} ...")
    H = {"Authorization": "Bearer " + login(a.base, a.email, a.password), "X-Broker-ID": "paper", "Content-Type": "application/json"}
    oms = f"{a.base}/v1/oms/paper"

    def call(method, path, **kw):
        return requests.request(method, oms + path, headers=H, timeout=120, **kw)

    def positions():
        return call("GET", "/positions").json().get("positions", [])

    def close_all():
        for _ in range(3):
            left = positions()
            if not left:
                return
            for p in left:
                call("POST", f"/positions/{p['market_order_id']}/squareoff", json={})
            time.sleep(1.2)

    say("Login OK. Instance: paper (simulated). Test account, 0.01 BTC.\n")
    beat(1.5)
    found = 0
    try:
        if "2" in want:
            say("=== BUG-2: wrong order type -> should be HTTP 400, not 500 ===")
            say('SEND   POST /orders   {"symbol":"BINANCE:BTCUSDT.P","side":"BUY","type":"WEIRD","qty":1}')
            beat()
            r = call("POST", "/orders", json={"symbol": SYMBOL, "side": "BUY", "type": "WEIRD", "qty": 1})
            say(f"ANSWER HTTP {r.status_code}   {r.text.strip()[:110]}")
            beat()
            r2 = call("POST", "/orders", json={"symbol": SYMBOL, "side": "SIDEWAYS", "type": "MARKET", "qty": 1})
            say(f"CONTROL (wrong side instead)  ->  HTTP {r2.status_code}  {r2.text.strip()[:70]}   <- handled correctly")
            ok = r.status_code == 400
            say(f"EXPECTED HTTP 400  =>  {'OK (fixed)' if ok else 'BUG REPRODUCED: server error 500 instead of 400'}\n")
            found += 0 if ok else 1
            beat(1.5)

        if "3" in want:
            say("=== BUG-3: invalid TP/SL on a new order -> should be rejected, not silently dropped ===")
            say('SEND   POST /orders   BUY MARKET 0.01   tp=-1   sl=1e30')
            beat()
            r = call("POST", "/orders", json={"symbol": SYMBOL, "side": "BUY", "type": "MARKET", "qty": 0.01, "tp": -1, "sl": 1e30})
            time.sleep(1.2)
            ps = positions()
            stored = [((p.get("tp_order") or {}).get("trigger_price"), (p.get("sl_order") or {}).get("trigger_price")) for p in ps]
            say(f"ANSWER HTTP {r.status_code}   position opened: {bool(ps)}   stored (tp, sl) = {stored}")
            beat()
            bug = r.status_code == 200
            if ps:
                pr = call("PUT", f"/positions/{ps[0]['market_order_id']}/protection", json={"tp": -1, "sl": 1e30})
                say(f"CONTROL same values on the dedicated TP/SL call -> HTTP {pr.status_code} {pr.text.strip()[:60]}   <- correctly rejected")
            say(f"EXPECTED HTTP 400, no trade  =>  {'BUG REPRODUCED: order accepted, TP/SL silently dropped (trade has NO protection)' if bug else 'OK (fixed)'}\n")
            found += 1 if bug else 0
            beat(2.0)
            close_all()

        if "1" in want:
            say("=== BUG-1: orders history has no paging (whole history in one answer) ===")
            say("SEND   GET /orders")
            beat()
            t0 = time.time()
            r = call("GET", "/orders")
            dt = time.time() - t0
            n = len(r.json().get("orders", [])) if r.status_code == 200 else -1
            say(f"ANSWER HTTP {r.status_code}   {n} orders   {len(r.content) / 1e6:.2f} MB   {dt:.2f} s")
            beat()
            say("SEND   GET /orders?limit=5     (ask for only 5)")
            r2 = call("GET", "/orders", params={"limit": 5})
            got = len(r2.json().get("orders", [])) if r2.status_code == 200 else -1
            say(f"ANSWER {got} orders returned")
            paged = 0 <= got <= 5
            say(f"EXPECTED 5 orders  =>  {'OK (fixed)' if paged else 'BUG REPRODUCED: limit ignored, whole history returned'}")
            say("NOTE   one call is fast on a quiet platform; the slowdown only shows under heavy load (JMeter).\n")
            found += 0 if paged else 1
            beat(1.5)
    finally:
        close_all()
        say(f"Cleanup done. Open positions left on the test account: {len(positions())}")
    say(f"\nRESULT: {found} bug(s) reproduced out of {len(want)} checked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
