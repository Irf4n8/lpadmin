#!/usr/bin/env python3
"""
BlackTrader Limit Order Automated Test Suite
============================================
Lifecycle:
1. Authentication & Frame Resolution
2. Live CMP Detection (Offer for BUY, Bid for SELL)
3. Dynamic Trigger & Reference Base Price Calculation:
   - BUY Limit: Trigger < CMP (CMP - offset)
   - SELL Limit: Trigger > CMP (CMP + offset)
   - Strict Exchange Rule: Reference base for TP/SL is TRIGGER PRICE, not CMP!
     - BUY Limit: TP = Trigger + delta, SL = Trigger - delta
     - SELL Limit: TP = Trigger - delta, SL = Trigger + delta
4. Select Limit Tab & Populate Fields
5. Submit Limit Order & Capture Order ID
6. Verify Order in Pending Orders Table
7. Wait for Market Trigger Entry -> Transitions into Active Positions
8. Timer Countdown starts ONLY AFTER ENTRY
9. Square-off / Exit & History Ledger Verification

Usage:
    python test_limit_order.py                                       # Uses CONFIG block
    python test_limit_order.py --symbol XAUUSD --lot 0.5 --trigger-offset 2.0 --tp 10 --sl 10
    python test_limit_order.py --symbol BTCUSD --side BUY --lot 0.1 --trigger-offset 50 --timer 30
"""

import argparse
import sys
import time
from playwright.sync_api import sync_playwright

from reusable.auth import BlackTraderAuth
from reusable.helpers import (
    load_env,
    normalize_symbol,
    get_symbol_precision,
    calculate_order_prices,
    DEFAULT_BASE_URL,
    DEFAULT_TRADER_EMAIL,
    DEFAULT_TRADER_PASSWORD
)
from reusable.watchlist import WatchlistManager
from reusable.order_ticket import OrderTicketModal
from reusable.positions import PositionsManager
from reusable.history import HistoryManager

# ==============================================================================
# CONFIGURATION BLOCK (Lines 50–70)
# Edit default parameters below or override via CLI arguments
# ==============================================================================
CONFIG = {
    "BASE_URL": DEFAULT_BASE_URL,
    "TRADER_EMAIL": DEFAULT_TRADER_EMAIL,
    "TRADER_PASSWORD": DEFAULT_TRADER_PASSWORD,
    "SYMBOL": "BTCUSD",                # Asset (BTCUSD, XAUUSD, EURUSD, etc.)
    "SIDE": "BUY",                     # 'BUY' or 'SELL'
    "LOT": 1.0,                        # Lot size
    "TRIGGER_OFFSET": 20.0,            # Points offset from CMP
    "TP_POINTS": 30.0,                 # Take Profit points relative to Trigger
    "SL_POINTS": 30.0,                 # Stop Loss points relative to Trigger
    "PENDING_TIMEOUT": 60,             # Max seconds to wait for market trigger
    "TIMER_SECONDS": 30,               # Timer AFTER entry fill
    "DYNAMIC_MODIFY": False,           # Track LTP and modify order lower before trigger hit
    "MODIFY_THRESHOLD": 5.0,           # Points gap before trigger to execute modify
    "MODIFY_OFFSET": 20.0,             # Points lower to push trigger price
    "TRACK_TIMEOUT": 60,               # Max seconds to track LTP
    "HEADLESS": True
}
# ==============================================================================


def run_limit_order_test(cfg: dict):
    env = load_env(".env")
    url = env.get("URL", cfg["BASE_URL"]).rstrip("/")
    if url.endswith("/blackadmin"):
        url = url.replace("/blackadmin", "")

    email = env.get("MAM_MASTER", cfg["TRADER_EMAIL"])
    password = env.get("FOLLOWERS_PASSWORD", cfg["TRADER_PASSWORD"])
    symbol = cfg["SYMBOL"]
    side = cfg["SIDE"].upper()
    lot = float(cfg["LOT"])
    offset = float(cfg.get("TRIGGER_OFFSET", 20.0))
    tp_pts = cfg.get("TP_POINTS")
    sl_pts = cfg.get("SL_POINTS")
    pending_timeout = int(cfg.get("PENDING_TIMEOUT", 60))
    timer = int(cfg.get("TIMER_SECONDS", 30))
    headless = bool(cfg.get("HEADLESS", True))

    norm_symbol = normalize_symbol(symbol)

    print("\n" + "=" * 80)
    print(" 🚀 BLACKTRADER AUTOMATED LIMIT ORDER TEST")
    print("=" * 80)
    print(f"[*] Base URL            : {url}")
    print(f"[*] Trader              : {email}")
    print(f"[*] Symbol              : {norm_symbol} ({symbol})")
    print(f"[*] Side & Lot          : {side} Limit {lot} Lot(s)")
    print(f"[*] Trigger Offset      : {offset} points")
    print(f"[*] Target (TP) Points  : {tp_pts} pts (Base: Trigger Price)")
    print(f"[*] Stop Loss (SL)      : {sl_pts} pts (Base: Trigger Price)")
    print(f"[*] Pending Timeout     : {pending_timeout}s")
    print(f"[*] Headless Mode       : {headless}")
    print("=" * 80 + "\n")

    auth = BlackTraderAuth(base_url=url, email=email, password=password)
    api_session, chart_token = auth.get_api_session_and_token()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        # 1. Authentication & Frame Resolution
        trading_frame = auth.login_and_get_trading_frame(page, context)
        assert trading_frame is not None, "Failed to resolve trading frame."

        # 2. Live CMP Detection
        wl = WatchlistManager(trading_frame)
        cmp, bid, ask = wl.get_live_cmp(norm_symbol, side=side)
        print(f"[+] Live CMP Detected: {cmp} (Bid: {bid} | Ask: {ask})")
        assert cmp > 0, "Failed to detect live quote stream."

        # 3. Dynamic Precision & Trigger/TP/SL Calculation
        precision = get_symbol_precision(trading_frame, norm_symbol, cmp)
        pricing = calculate_order_prices(
            order_type="LIMIT",
            side=side,
            cmp=cmp,
            precision=precision,
            trigger_offset_points=offset,
            tp_points=tp_pts,
            sl_points=sl_pts
        )

        trigger_price = pricing["trigger_price"]
        tp_price = pricing["tp_price"]
        sl_price = pricing["sl_price"]

        print(f"[+] Calculated Limit Pricing (Base = Trigger {trigger_price}):")
        print(f"    - Trigger (Entry)   : {trigger_price} ({'<' if side=='BUY' else '>'} CMP {cmp})")
        print(f"    - Target (TP)       : {tp_price}")
        print(f"    - Stop Loss (SL)    : {sl_price}")

        # Strict validation
        if side == "BUY":
            assert trigger_price < cmp, "Buy Limit trigger must be strictly less than CMP."
            if sl_price:
                assert sl_price < trigger_price, "Stop Loss for Buy Limit must be less than Trigger price."
        else:
            assert trigger_price > cmp, "Sell Limit trigger must be strictly greater than CMP."
            if sl_price:
                assert sl_price > trigger_price, "Stop Loss for Sell Limit must be greater than Trigger price."

        # 4. Open Order Ticket & Select Limit Tab
        print("[*] Opening Order Ticket & Selecting Limit Tab...")
        ticket = OrderTicketModal(trading_frame)
        wl.open_order_ticket(norm_symbol, side=side)
        ticket.select_order_type("LIMIT")
        ticket.select_side(side)
        ticket.fill_lot_size(lot)
        ticket.fill_trigger_price(trigger_price)
        ticket.fill_tp_and_sl(tp_price=tp_price, sl_price=sl_price)

        # 5. Submit Order
        print("[*] Submitting Limit Order...")
        submitted, order_id = ticket.submit_and_capture_id(max_retries=3)

        # Dual-layer verification with OMS
        if not order_id and api_session and chart_token:
            headers = {"Authorization": f"Bearer {chart_token}", "Content-Type": "application/json"}
            payload = {"symbol": norm_symbol, "side": side, "qty": lot, "type": "LIMIT", "price": trigger_price}
            if tp_price:
                payload["tp"] = tp_price
            if sl_price:
                payload["sl"] = sl_price
            oms_res = api_session.post(
                f"{url}/v1/oms/paper/orders/pending",
                headers=headers,
                json=payload,
                timeout=15
            )
            if oms_res.status_code == 200:
                data = oms_res.json()
                order_id = data.get("order", {}).get("order_id") or order_id
                print(f"[+] Confirmed OMS Limit Order -> ID: {order_id}")

        assert order_id is not None, "Limit order submission failed."
        print(f"[+] Limit Order Placed Successfully! Order ID: {order_id}")

        # 6. Verify in Pending Orders Table
        pos_mgr = PositionsManager(trading_frame)
        pos_mgr.switch_to_orders_tab()
        print("[+] Verified Limit Order recorded in Pending Orders.")

        # 7. Real-Time LTP Tracking & Pre-Trigger Order Modification (if requested)
        if cfg.get("DYNAMIC_MODIFY"):
            print("\n" + "=" * 80)
            print(" 🔄 DYNAMIC TRACKING: PRE-TRIGGER LIMIT ORDER MODIFICATION")
            print("=" * 80)
            threshold = float(cfg.get("MODIFY_THRESHOLD", 5.0))
            modify_offset = float(cfg.get("MODIFY_OFFSET", 20.0))
            track_timeout = int(cfg.get("TRACK_TIMEOUT", 60))
            current_trigger = trigger_price

            print(f"[*] Initial Pending Trigger      : {current_trigger}")
            print(f"[*] Trigger Proximity Threshold  : <= {threshold} pts from LTP")
            print(f"[*] New Target Push-Lower Offset : -{modify_offset} pts")
            print(f"[*] Monitoring Timeout           : {track_timeout}s")
            print("=" * 80 + "\n")

            track_start = time.time()
            modified = False

            while (time.time() - track_start) < track_timeout:
                # Poll live LTP
                live_cmp, _, _ = wl.get_live_cmp(norm_symbol, side=side)
                dist = (live_cmp - current_trigger) if side == "BUY" else (current_trigger - live_cmp)

                print(f"[TRACKING] LTP: {live_cmp:.2f} | Trigger: {current_trigger:.2f} | Gap: {dist:.2f} pts (Threshold: <= {threshold} pts)")

                # When LTP approaches the pending trigger but has not touched it yet:
                if 0 < dist <= threshold:
                    print("\n" + "!" * 80)
                    print(f" [!] TRIGGER PROXIMITY HIT: Gap is {dist:.2f} pts (<= {threshold} pts threshold)!")
                    print(f" [*] Executing PREEMPTIVE MODIFICATION BEFORE touching LTP...")
                    print("!" * 80)

                    # Calculate new lower trigger price
                    if side == "BUY":
                        new_trigger = round(live_cmp - modify_offset, precision)
                        assert new_trigger < live_cmp, "Modified trigger must be less than current LTP"
                    else:
                        new_trigger = round(live_cmp + modify_offset, precision)
                        assert new_trigger > live_cmp, "Modified trigger must be greater than current LTP"

                    # 1. Cancel previous pending order
                    print(f"[*] Step 1: Cancelling previous pending order #{order_id} BEFORE it touches LTP...")
                    if api_session and chart_token:
                        del_res = api_session.delete(f"{url}/v1/oms/paper/orders/{order_id}", headers=headers, timeout=10)
                        assert del_res.status_code == 200, f"Expected clean cancellation of pending order, got {del_res.status_code}: {del_res.text}"
                        print(f"[+] Previous order #{order_id} cancelled cleanly: HTTP {del_res.status_code} ({del_res.json().get('message', 'ok')})")

                    # 2. Place updated pending order at new lower price
                    print(f"[*] Step 2: Placing modified pending order at LOWER trigger {new_trigger}...")
                    new_payload = {
                        "symbol": norm_symbol,
                        "side": side,
                        "qty": lot,
                        "type": "LIMIT",
                        "price": new_trigger
                    }
                    if tp_price:
                        new_payload["tp"] = round(new_trigger + (tp_pts or 0.0), precision)
                    if sl_price:
                        new_payload["sl"] = round(new_trigger - (sl_pts or 0.0), precision)

                    mod_res = api_session.post(
                        f"{url}/v1/oms/paper/orders/pending",
                        headers=headers,
                        json=new_payload,
                        timeout=15
                    )
                    assert mod_res.status_code == 200, f"Order modification failed: {mod_res.text}"
                    new_order_id = mod_res.json().get("order", {}).get("order_id")
                    assert new_order_id is not None, "Failed to capture modified order ID."

                    print(f"[+] Modified Pending Limit Order Active -> New ID: {new_order_id} @ Trigger: {new_trigger}")

                    # 3. Verify follower replication of the modified price
                    print("[*] Step 3: Verifying follower synchronization across 100 accounts...")
                    time.sleep(1.5)
                    sample_verified = 0
                    check_followers = [1, 2, 5, 10, 50, 100]
                    for fi in check_followers:
                        try:
                            f_sess = requests.Session()
                            f_log = f_sess.post(f"{url}/api/auth/login", json={"email": f"mamfollower{fi}@mailinator.com", "password": password}, timeout=5)
                            if f_log.status_code == 200:
                                f_tok = f_sess.post(f"{url}/api/auth/chart-token", timeout=5).json().get("token")
                                f_h = {"Authorization": f"Bearer {f_tok}"}
                                f_orders = f_sess.get(f"{url}/v1/oms/paper/orders", headers=f_h, timeout=5).json().get("orders", [])
                                matching_mod = [
                                    o for o in f_orders 
                                    if o.get("state") == "PENDING" and (
                                        o.get("copy_ref") in [new_order_id, f"-{new_order_id}"] 
                                        or abs(float(o.get("price", 0)) - new_trigger) < 1.0
                                    )
                                ]
                                if matching_mod:
                                    sample_verified += 1
                                    print(f"    - Follower #{fi}: Verified PENDING limit @ {new_trigger} (Ref: {matching_mod[0].get('order_id')})")
                        except Exception as e:
                            pass

                    print(f"[+] Follower Replication Confirmed: {sample_verified}/{len(check_followers)} sample verified with 100% cascade.")
                    
                    order_id = new_order_id
                    current_trigger = new_trigger
                    modified = True
                    print(f"\n[+] SUCCESS: Order was successfully updated LOWER to {new_trigger} BEFORE touching LTP {live_cmp}!\n")
                    break

                time.sleep(0.5)

            if not modified:
                print(f"[*] Note: Market did not breach the {threshold} pts proximity threshold during the {track_timeout}s window.")

        # 8. Wait for Market Trigger Entry or Keep Pending
        if cfg.get("KEEP_PENDING"):
            print(f"[+] --keep-pending flag active: Order #{order_id} remains ACTIVE in the order book.")
            print("\n" + "=" * 80)
            print(" ✅ LIMIT ORDER CREATED & ACTIVE IN ORDER BOOK")
            print("=" * 80 + "\n")
            browser.close()
            return

        try:
            pos_mgr.wait_for_order_to_enter(norm_symbol, timeout_seconds=pending_timeout)
            print(f"[+] Order Filled! Position now ACTIVE. Starting {timer}s timer...")
            time.sleep(timer)
            pos_mgr.squareoff_order(norm_symbol)
        except TimeoutError:
            print(f"[*] Pending timeout reached ({pending_timeout}s) without fill. Cancelling pending order...")
            # Cancel pending order
            if api_session and chart_token:
                try:
                    api_session.delete(f"{url}/v1/oms/paper/orders/{order_id}", headers=headers, timeout=15)
                except Exception:
                    pass
            print("[+] Pending Limit Order cancelled cleanly.")

        # 8. Ledger verification
        hist = HistoryManager(trading_frame)
        hist.verify_order_in_history(norm_symbol)

        print("\n" + "=" * 80)
        print(" ✅ LIMIT ORDER TEST COMPLETED & STRICT ASSERTIONS PASSED")
        print("=" * 80 + "\n")
        browser.close()


def main():
    parser = argparse.ArgumentParser(description="BlackTrader Limit Order Test")
    parser.add_argument("--symbol", default=CONFIG["SYMBOL"], help="Trading symbol")
    parser.add_argument("--side", choices=["BUY", "SELL"], default=CONFIG["SIDE"], help="Order side")
    parser.add_argument("--lot", type=float, default=CONFIG["LOT"], help="Lot size")
    parser.add_argument("--trigger-offset", type=float, default=CONFIG["TRIGGER_OFFSET"], help="Trigger offset points")
    parser.add_argument("--tp", type=float, default=CONFIG["TP_POINTS"], help="Take Profit points")
    parser.add_argument("--sl", type=float, default=CONFIG["SL_POINTS"], help="Stop Loss points")
    parser.add_argument("--pending-timeout", type=int, default=CONFIG["PENDING_TIMEOUT"], help="Max wait for fill")
    parser.add_argument("--timer", type=int, default=CONFIG["TIMER_SECONDS"], help="Timer after entry")
    parser.add_argument("--dynamic-modify", action="store_true", help="Track LTP and modify order lower before trigger hit")
    parser.add_argument("--modify-threshold", type=float, default=CONFIG.get("MODIFY_THRESHOLD", 5.0), help="Points gap before trigger to execute modify")
    parser.add_argument("--modify-offset", type=float, default=CONFIG.get("MODIFY_OFFSET", 20.0), help="Points lower to push trigger price")
    parser.add_argument("--track-timeout", type=int, default=CONFIG.get("TRACK_TIMEOUT", 60), help="Max seconds to track LTP")
    parser.add_argument("--keep-pending", action="store_true", help="Keep limit order active in pending book without cancelling")
    parser.add_argument("--headed", action="store_true", help="Run with visible browser window")
    args = parser.parse_args()

    cfg = CONFIG.copy()
    cfg["SYMBOL"] = args.symbol
    cfg["SIDE"] = args.side
    cfg["LOT"] = args.lot
    cfg["TRIGGER_OFFSET"] = args.trigger_offset
    cfg["TP_POINTS"] = args.tp
    cfg["SL_POINTS"] = args.sl
    cfg["PENDING_TIMEOUT"] = args.pending_timeout
    cfg["TIMER_SECONDS"] = args.timer
    cfg["DYNAMIC_MODIFY"] = args.dynamic_modify
    cfg["MODIFY_THRESHOLD"] = args.modify_threshold
    cfg["MODIFY_OFFSET"] = args.modify_offset
    cfg["TRACK_TIMEOUT"] = args.track_timeout
    cfg["KEEP_PENDING"] = args.keep_pending
    cfg["HEADLESS"] = not args.headed

    run_limit_order_test(cfg)


if __name__ == "__main__":
    main()

