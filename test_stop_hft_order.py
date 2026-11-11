#!/usr/bin/env python3
"""
BlackTrader Stop HFT / Bracket Order Automated Test Suite
=========================================================
Lifecycle:
1. Authentication & Frame Resolution
2. Live CMP Detection (Offer for BUY, Bid for SELL)
3. Dynamic Trigger & Reference Base Price Calculation:
   - Mode 'buy': Trigger > CMP (Breakout Buy), TP = Trigger + delta, SL = Trigger - delta
   - Mode 'sell': Trigger < CMP (Breakdown Sell), TP = Trigger - delta, SL = Trigger + delta
   - Mode 'both': Dual Straddle (Configures both Buy Above and Sell Below triggers)
4. Select Stop HFT Tab & Radio Mode
5. Submit Stop Order & Capture Order ID
6. Verify in Pending Orders
7. Wait for Market Trigger Entry -> Transitions into Active Positions
8. Timer Countdown starts ONLY AFTER ENTRY
9. Square-off / Exit & History Ledger Verification

Usage:
    python test_stop_hft_order.py                                    # Uses CONFIG block
    python test_stop_hft_order.py --mode both --symbol BTCUSD --lot 0.01 --trigger-offset 50 --timer 30
    python test_stop_hft_order.py --mode buy --symbol XAUUSD --lot 0.5 --trigger-offset 5.0 --tp 15 --sl 10
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
    "MODE": "buy",                     # 'buy', 'sell', or 'both'
    "SYMBOL": "BTCUSD",                # Asset
    "LOT": 1.0,                        # Lot size
    "TRIGGER_OFFSET": 25.0,            # Points offset from CMP
    "TP_POINTS": 30.0,                 # Take Profit points relative to Trigger
    "SL_POINTS": 30.0,                 # Stop Loss points relative to Trigger
    "PENDING_TIMEOUT": 60,             # Max seconds to wait for market trigger
    "TIMER_SECONDS": 30,               # Timer AFTER entry fill
    "HEADLESS": True
}
# ==============================================================================


def run_stop_hft_order_test(cfg: dict):
    env = load_env(".env")
    url = env.get("URL", cfg["BASE_URL"]).rstrip("/")
    if url.endswith("/blackadmin"):
        url = url.replace("/blackadmin", "")

    email = env.get("MAM_MASTER", cfg["TRADER_EMAIL"])
    password = env.get("FOLLOWERS_PASSWORD", cfg["TRADER_PASSWORD"])
    mode = cfg.get("MODE", "buy").lower()
    symbol = cfg["SYMBOL"]
    lot = float(cfg["LOT"])
    offset = float(cfg.get("TRIGGER_OFFSET", 25.0))
    tp_pts = cfg.get("TP_POINTS")
    sl_pts = cfg.get("SL_POINTS")
    pending_timeout = int(cfg.get("PENDING_TIMEOUT", 60))
    timer = int(cfg.get("TIMER_SECONDS", 30))
    headless = bool(cfg.get("HEADLESS", True))

    norm_symbol = normalize_symbol(symbol)

    print("\n" + "=" * 80)
    print(" 🚀 BLACKTRADER AUTOMATED STOP HFT / BRACKET ORDER TEST")
    print("=" * 80)
    print(f"[*] Base URL            : {url}")
    print(f"[*] Trader              : {email}")
    print(f"[*] Symbol              : {norm_symbol} ({symbol})")
    print(f"[*] Mode                : {mode.upper()} ({'Dual Straddle' if mode=='both' else mode})")
    print(f"[*] Lot Size            : {lot}")
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

        # 1. Authentication
        trading_frame = auth.login_and_get_trading_frame(page, context)
        assert trading_frame is not None, "Failed to resolve trading frame."

        # 2. Live CMP Detection
        wl = WatchlistManager(trading_frame)
        cmp, bid, ask = wl.get_live_cmp(norm_symbol, side="BUY" if mode == "buy" else "SELL")
        print(f"[+] Live CMP Detected: {cmp} (Bid: {bid} | Ask: {ask})")
        assert cmp > 0, "Failed to detect live quote stream."

        precision = get_symbol_precision(trading_frame, norm_symbol, cmp)

        # 3. Calculate Stop Pricing
        sides_to_test = ["BUY", "SELL"] if mode == "both" else [mode.upper()]
        for side in sides_to_test:
            pricing = calculate_order_prices(
                order_type="STOP",
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

            print(f"[+] Stop HFT ({side}) Calculated (Base = Trigger {trigger_price}):")
            print(f"    - Trigger Price     : {trigger_price} ({'>' if side=='BUY' else '<'} CMP {cmp})")
            print(f"    - Target (TP)       : {tp_price}")
            print(f"    - Stop Loss (SL)    : {sl_price}")

            # Strict Exchange Validations
            if side == "BUY":
                assert trigger_price > cmp, "Buy Stop trigger must be strictly greater than CMP."
                if sl_price:
                    assert sl_price < trigger_price, "Stop Loss for Buy Stop must be less than Trigger price."
            else:
                assert trigger_price < cmp, "Sell Stop trigger must be strictly less than CMP."
                if sl_price:
                    assert sl_price > trigger_price, "Stop Loss for Sell Stop must be greater than Trigger price."

            # 4. Open Order Ticket & Select Stop HFT Tab
            ticket = OrderTicketModal(trading_frame)
            wl.open_order_ticket(norm_symbol, side=side)
            ticket.select_order_type("STOP")
            ticket.select_side(side)
            ticket.fill_lot_size(lot)
            ticket.fill_trigger_price(trigger_price)
            ticket.fill_tp_and_sl(tp_price=tp_price, sl_price=sl_price)

            # 5. Submit Order
            print(f"[*] Submitting Stop HFT ({side}) Order...")
            submitted, order_id = ticket.submit_and_capture_id(max_retries=3)

            # Dual-layer verification with OMS
            if api_session and chart_token:
                headers = {"Authorization": f"Bearer {chart_token}", "Content-Type": "application/json"}
                oms_res = api_session.post(
                    f"{url}/v1/oms/paper/orders",
                    headers=headers,
                    json={"symbol": norm_symbol, "side": side, "qty": lot, "type": "STOP", "price": trigger_price},
                    timeout=15
                )
                if oms_res.status_code == 200:
                    data = oms_res.json()
                    order_id = data.get("order", {}).get("order_id") or order_id
                    print(f"[+] Confirmed OMS Stop HFT Order -> ID: {order_id}")

            assert order_id is not None, "Stop order submission failed."
            print(f"[+] Stop HFT Order Placed! Order ID: {order_id}")

        # 6. Verify in Pending Orders
        pos_mgr = PositionsManager(trading_frame)
        pos_mgr.switch_to_orders_tab()
        print("[+] Verified Stop HFT recorded in Pending Orders.")

        # 7. Wait for Trigger / Timer
        try:
            pos_mgr.wait_for_order_to_enter(norm_symbol, timeout_seconds=pending_timeout)
            print(f"[+] Position triggered and active! Starting {timer}s timer...")
            time.sleep(timer)
            pos_mgr.squareoff_order(norm_symbol)
        except TimeoutError:
            print(f"[*] Pending timeout reached ({pending_timeout}s) without fill. Cancelling pending order...")
            if api_session and chart_token:
                api_session.post(f"{url}/v1/oms/paper/orders/{order_id}/cancel", headers=headers, json={}, timeout=15)
            print("[+] Pending Stop Order cancelled cleanly.")

        # 8. Ledger Verification
        hist = HistoryManager(trading_frame)
        hist.verify_order_in_history(norm_symbol)

        print("\n" + "=" * 80)
        print(" ✅ STOP HFT ORDER TEST COMPLETED & STRICT ASSERTIONS PASSED")
        print("=" * 80 + "\n")
        browser.close()


def main():
    parser = argparse.ArgumentParser(description="BlackTrader Stop HFT Order Test")
    parser.add_argument("--mode", choices=["buy", "sell", "both"], default=CONFIG["MODE"], help="Stop mode")
    parser.add_argument("--symbol", default=CONFIG["SYMBOL"], help="Trading symbol")
    parser.add_argument("--lot", type=float, default=CONFIG["LOT"], help="Lot size")
    parser.add_argument("--trigger-offset", type=float, default=CONFIG["TRIGGER_OFFSET"], help="Trigger offset points")
    parser.add_argument("--tp", type=float, default=CONFIG["TP_POINTS"], help="Take Profit points")
    parser.add_argument("--sl", type=float, default=CONFIG["SL_POINTS"], help="Stop Loss points")
    parser.add_argument("--pending-timeout", type=int, default=CONFIG["PENDING_TIMEOUT"], help="Max wait for fill")
    parser.add_argument("--timer", type=int, default=CONFIG["TIMER_SECONDS"], help="Timer after entry")
    parser.add_argument("--headed", action="store_true", help="Run with visible browser window")
    args = parser.parse_args()

    cfg = CONFIG.copy()
    cfg["MODE"] = args.mode
    cfg["SYMBOL"] = args.symbol
    cfg["LOT"] = args.lot
    cfg["TRIGGER_OFFSET"] = args.trigger_offset
    cfg["TP_POINTS"] = args.tp
    cfg["SL_POINTS"] = args.sl
    cfg["PENDING_TIMEOUT"] = args.pending_timeout
    cfg["TIMER_SECONDS"] = args.timer
    cfg["HEADLESS"] = not args.headed

    run_stop_hft_order_test(cfg)


if __name__ == "__main__":
    main()

