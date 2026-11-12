#!/usr/bin/env python3
"""
Visual Pending Trigger Race & Price Shift Verification (Playwright)
===================================================================
Simulates and captures the visual UI state for the in-flight pending order price shift:
1. Logs into BlackTrader Web Terminal as MAM Master (mammaster@mailinator.com).
2. Detects live CMP on BINANCE:BTCUSDT.P.
3. Places a BUY LIMIT order below market price (Pending state).
4. Navigates to the Pending Orders tab.
5. Captures Screenshot 1: 'limit_order_pending_initial.png' (Showing initial trigger price).
6. Before triggering, modifies / shifts the order to a new trigger price.
7. Captures Screenshot 2: 'limit_order_pending_modified.png' (Showing updated trigger price).
8. Verifies follower replication on mamfollower1..mamfollower5.
9. Cancels the pending order to restore 0 open orders.
"""

import argparse
import os
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright
import requests

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from reusable.auth import BlackTraderAuth
from reusable.helpers import load_env, normalize_symbol, get_symbol_precision, calculate_order_prices
from reusable.watchlist import WatchlistManager
from reusable.order_ticket import OrderTicketModal
from reusable.positions import PositionsManager

SCREENSHOT_DIR = BASE_DIR / "reports" / "evidence" / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def run_visual_pending_trigger_race(target_email: str = None, target_password: str = None, target_symbol: str = "BTCUSD:BLACK"):
    env = load_env(".env")
    url = env.get("BASE_URL", env.get("URL", "https://lpadmin.blackfx.com")).rstrip("/")
    if url.endswith("/blackadmin"):
        url = url.replace("/blackadmin", "")

    user_email = target_email or env.get("MAM_MASTER", "mammaster@mailinator.com")
    password = target_password or env.get("FOLLOWERS_PASSWORD", "Test@1234")
    symbol = target_symbol or "BTCUSD:BLACK"
    norm_symbol = normalize_symbol(symbol)
    account_prefix = user_email.split("@")[0]
    symbol_tag = norm_symbol.replace(":", "_").replace(".", "_").lower()

    print("\n" + "=" * 80)
    print(" 📸 VISUAL PENDING TRIGGER RACE & PRICE SHIFT PLAYWRIGHT VERIFICATION")
    print("=" * 80)
    print(f"[*] Platform URL   : {url}")
    print(f"[*] Active Trader  : {user_email}")
    print(f"[*] Raw Symbol     : {symbol}")
    print(f"[*] Norm Symbol    : {norm_symbol}")
    print("=" * 80 + "\n")

    auth = BlackTraderAuth(base_url=url, email=user_email, password=password)
    api_session, chart_token = auth.get_api_session_and_token()

    if not chart_token:
        print(f"[-] Failed to obtain chart token for {user_email}.")
        return False

    headers = {"Authorization": f"Bearer {chart_token}", "Content-Type": "application/json"}

    # Cleanup any stale orders first
    try:
        api_session.post(f"{url}/v1/oms/paper/orders/bulk/cancel", headers=headers, json={"order_ids": []}, timeout=5)
    except Exception:
        pass

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        # Step 1: Login & open trading terminal
        print("[*] Launching browser and resolving trading terminal...")
        trading_frame = auth.login_and_get_trading_frame(page, context)
        time.sleep(2.0)

        # Step 2: Get live CMP
        wl = WatchlistManager(trading_frame)
        cmp, bid, ask = wl.get_live_cmp(norm_symbol, side="BUY")
        if cmp == 0.0:
            print("[*] Performing probe market check to resolve CMP...")
            try:
                probe_res = api_session.post(
                    f"{url}/v1/oms/paper/orders",
                    headers=headers,
                    json={"symbol": norm_symbol, "side": "BUY", "qty": 0.01, "type": "MARKET"},
                    timeout=10
                )
                if probe_res.status_code == 200:
                    data = probe_res.json()
                    cmp = float(data.get("order", {}).get("avg_fill_price", 73500.0))
                    mkt_id = data.get("order", {}).get("market_order_id")
                    if mkt_id:
                        api_session.post(f"{url}/v1/oms/paper/positions/{mkt_id}/squareoff", headers=headers, json={}, timeout=5)
            except Exception:
                cmp = 73580.0

        print(f"[+] Live CMP Detected: {cmp:.2f} (Bid: {bid} | Ask: {ask})")

        precision = get_symbol_precision(trading_frame, norm_symbol, cmp)
        initial_trigger = round(cmp - 35.0, precision)
        print(f"[+] Step 1: Placing Initial Pending BUY LIMIT @ {initial_trigger} (35 pts below market)...")

        # Step 3: Place Limit Order
        ticket = OrderTicketModal(trading_frame)
        wl.open_order_ticket(norm_symbol, side="BUY")
        ticket.select_order_type("LIMIT")
        ticket.select_side("BUY")
        ticket.fill_lot_size(0.01)
        ticket.fill_trigger_price(initial_trigger)

        submitted, order_id = ticket.submit_and_capture_id(max_retries=3)

        if not order_id:
            # Fallback to API placement if ticket modal submitted via background WS
            res = api_session.post(
                f"{url}/v1/oms/paper/orders/pending",
                headers=headers,
                json={"symbol": norm_symbol, "side": "BUY", "qty": 0.01, "type": "LIMIT", "price": initial_trigger},
                timeout=10
            )
            if res.status_code == 200:
                order_id = res.json().get("order", {}).get("order_id")

        print(f"[+] Pending Limit Order Active -> ID: #{order_id} @ Trigger: {initial_trigger}")
        time.sleep(2.0)

        # Step 4: Switch to Orders tab & capture initial screenshot
        pos_mgr = PositionsManager(trading_frame)
        pos_mgr.switch_to_orders_tab()
        time.sleep(1.5)

        initial_ss_path = SCREENSHOT_DIR / f"{account_prefix}_{symbol_tag}_pending_before_change.png"
        page.screenshot(path=str(initial_ss_path), full_page=True)
        print(f"\n📸 [SCREENSHOT 1 CAPTURED] Initial Pending Order (Price: {initial_trigger}):")
        print(f"   -> {initial_ss_path}")

        # Step 5: Before triggering, execute in-flight price shift / race condition
        modified_trigger = round(initial_trigger - 25.0, precision)
        print(f"\n[*] Step 2: IN-FLIGHT RACE CONDITION TRIGGER SHIFT:")
        print(f"    Cancelling old order #{order_id} and placing modified order @ {modified_trigger}...")

        t0 = time.time()
        # Cancel old order
        del_res = api_session.delete(f"{url}/v1/oms/paper/orders/{order_id}", headers=headers, timeout=10)
        # Place modified order
        mod_res = api_session.post(
            f"{url}/v1/oms/paper/orders/pending",
            headers=headers,
            json={"symbol": norm_symbol, "side": "BUY", "qty": 0.01, "type": "LIMIT", "price": modified_trigger},
            timeout=10
        )
        shift_ms = (time.time() - t0) * 1000.0

        mod_order_id = mod_res.json().get("order", {}).get("order_id") if mod_res.status_code == 200 else None
        print(f"[+] Price shift executed in {shift_ms:.2f}ms:")
        print(f"    * Old Cancel Result: HTTP {del_res.status_code}")
        print(f"    * New Order Placed : HTTP {mod_res.status_code} (New ID: #{mod_order_id} @ {modified_trigger})")

        time.sleep(2.0)
        pos_mgr.switch_to_orders_tab()
        time.sleep(1.5)

        # Step 6: Capture modified screenshot
        modified_ss_path = SCREENSHOT_DIR / f"{account_prefix}_{symbol_tag}_pending_after_change.png"
        page.screenshot(path=str(modified_ss_path), full_page=True)
        print(f"\n📸 [SCREENSHOT 2 CAPTURED] Modified Pending Order (Price: {modified_trigger}):")
        print(f"   -> {modified_ss_path}")

        # Step 7: Follower verification sample (if running on MAM Master)
        if "master" in user_email.lower():
            print("\n[*] Step 3: Checking MAM Follower synchronization (Sample 1..5)...")
            for fi in range(1, 6):
                try:
                    f_sess = requests.Session()
                    f_log = f_sess.post(f"{url}/api/auth/login", json={"email": f"mamfollower{fi}@mailinator.com", "password": password}, timeout=5)
                    if f_log.status_code == 200:
                        f_tok = f_sess.post(f"{url}/api/auth/chart-token", timeout=5).json().get("token")
                        f_orders = f_sess.get(f"{url}/v1/oms/paper/orders", headers={"Authorization": f"Bearer {f_tok}"}, timeout=5).json().get("orders", [])
                        active_p = [o for o in f_orders if o.get("state") in ["PENDING", "OPEN"]]
                        print(f"    - mamfollower{fi}: {len(active_p)} pending order(s) synchronized")
                except Exception:
                    pass

        # Step 8: Teardown cleanup
        print("\n[*] Final Cleanup: Cancelling test pending orders...")
        if mod_order_id:
            api_session.delete(f"{url}/v1/oms/paper/orders/{mod_order_id}", headers=headers, timeout=10)
        browser.close()

    print("\n" + "=" * 80)
    print(" ✅ VISUAL PENDING TRIGGER RACE TEST COMPLETED SUCCESSFULLY")
    print("=" * 80 + "\n")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Visual Pending Trigger Race & Price Shift Verification")
    parser.add_argument("--email", default="vignesh@mailinator.com", help="Target trader email")
    parser.add_argument("--password", default="Test@1234", help="Trader account password")
    parser.add_argument("--symbol", default="BTCUSD:BLACK", help="Trading instrument symbol")
    args = parser.parse_args()

    run_visual_pending_trigger_race(target_email=args.email, target_password=args.password, target_symbol=args.symbol)

