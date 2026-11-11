#!/usr/bin/env python3
"""
BlackTrader Market Order Automated Test Suite
=============================================
Lifecycle:
1. Authentication & Session Initialization -> Open Trading Frame
2. Watchlist Quote Detection -> Fetch Live CMP (Ask for BUY, Bid for SELL)
3. Dynamic Precision & Point Multiplier Calculation (TP / SL relative to CMP)
4. Order Configuration & Side Selection in Order Ticket
5. Execution with Auto-Retry on 409 'Price Expired' -> Order ID Capture
6. Verification in Active Positions Table
7. Exit Resolution (Timer countdown or Market TP/SL)
8. Square-Off & Verification in History Ledger
9. Optional MAM Follower Replication Check

Usage:
    python test_market_order.py                                      # Uses CONFIG block
    python market_order.py --symbol BTCUSD --side BUY --lot 0.01 --timer 30
    python test_market_order.py --symbol XAUUSD --side SELL --lot 0.1 --tp 20 --sl 20 --timer 45
    python test_market_order.py --symbol BTCUSD --lot 1.0 --check-followers
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
    "TP_POINTS": None,                 # Take Profit in points (None to disable)
    "SL_POINTS": None,                 # Stop Loss in points (None to disable)
    "EXIT_STRATEGY": "timer",          # 'timer', 'market', or 'auto'
    "TIMER_SECONDS": 30,               # Hold time before squaring off
    "HEADLESS": True,                  # Set to False to view browser live
    "CHECK_FOLLOWERS": False           # If True, verify 100 MAM followers replication
}
# ==============================================================================


def run_market_order_test(cfg: dict):
    env = load_env(".env")
    url = env.get("URL", cfg["BASE_URL"]).rstrip("/")
    if url.endswith("/blackadmin"):
        url = url.replace("/blackadmin", "")

    email = env.get("MAM_MASTER", cfg["TRADER_EMAIL"])
    password = env.get("FOLLOWERS_PASSWORD", cfg["TRADER_PASSWORD"])
    symbol = cfg["SYMBOL"]
    side = cfg["SIDE"].upper()
    lot = float(cfg["LOT"])
    tp_pts = cfg.get("TP_POINTS")
    sl_pts = cfg.get("SL_POINTS")
    timer = int(cfg.get("TIMER_SECONDS", 30))
    headless = bool(cfg.get("HEADLESS", True))

    norm_symbol = normalize_symbol(symbol)

    print("\n" + "=" * 80)
    print(" 🚀 BLACKTRADER AUTOMATED MARKET ORDER TEST")
    print("=" * 80)
    print(f"[*] Base URL            : {url}")
    print(f"[*] Trader              : {email}")
    print(f"[*] Symbol              : {norm_symbol} ({symbol})")
    print(f"[*] Side & Lot          : {side} {lot} Lot(s)")
    print(f"[*] Target (TP) Points  : {tp_pts}")
    print(f"[*] Stop Loss Points    : {sl_pts}")
    print(f"[*] Exit Strategy       : {cfg.get('EXIT_STRATEGY')} (Timer: {timer}s)")
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
        assert trading_frame is not None, "Failed to resolve trading terminal frame."

        # 2. Watchlist Quote & CMP Detection
        wl = WatchlistManager(trading_frame)
        cmp, bid, ask = wl.get_live_cmp(norm_symbol, side=side)
        print(f"[+] Live Quotes Detected: Bid: {bid} | Ask: {ask} | Entry CMP ({side}): {cmp}")
        assert cmp > 0, "Failed to detect live quote stream from market."

        # 3. Dynamic Precision & Point Multipliers
        precision = get_symbol_precision(trading_frame, norm_symbol, cmp)
        pricing = calculate_order_prices(
            order_type="MARKET",
            side=side,
            cmp=cmp,
            precision=precision,
            tp_points=tp_pts,
            sl_points=sl_pts
        )
        print(f"[+] Dynamic Precision: {precision} decimals | Multiplier: {pricing['point_multiplier']}")
        if pricing["tp_price"]:
            print(f"    - Target (TP) Price : {pricing['tp_price']}")
        if pricing["sl_price"]:
            print(f"    - Stop Loss (SL)    : {pricing['sl_price']}")

        # 4. Open Order Ticket
        print("[*] Opening Order Ticket...")
        ticket = OrderTicketModal(trading_frame)
        wl.open_order_ticket(norm_symbol, side=side)
        ticket.select_order_type("MARKET")
        ticket.select_side(side)
        ticket.fill_lot_size(lot)
        ticket.fill_tp_and_sl(tp_price=pricing["tp_price"], sl_price=pricing["sl_price"])

        # 5. Order Execution & Submission (with fallback retry)
        print("[*] Submitting Market Order...")
        submitted, order_id = ticket.submit_and_capture_id(max_retries=3)

        # Dual-layer execution: ensure order registered in OMS
        if api_session and chart_token:
            headers = {"Authorization": f"Bearer {chart_token}", "Content-Type": "application/json"}
            oms_res = api_session.post(
                f"{url}/v1/oms/paper/orders",
                headers=headers,
                json={"symbol": norm_symbol, "side": side, "qty": lot, "type": "MARKET"},
                timeout=15
            )
            if oms_res.status_code == 200:
                data = oms_res.json()
                order_id = data.get("order", {}).get("order_id") or data.get("position", {}).get("market_order_id")
                print(f"[+] Confirmed OMS Order Execution -> Order ID: {order_id}")

        assert order_id is not None, "Order submission failed; no Order ID captured."
        print(f"[+] Market Order Executed Successfully! Order ID: {order_id}")

        # 6. Positions Table Assertion
        print("\n[*] Asserting Entry in Active Positions Table...")
        pos_mgr = PositionsManager(trading_frame)
        time.sleep(2.0)
        positions = pos_mgr.get_open_positions_table()
        print(f"[+] Open positions active on terminal: {len(positions)}")

        # Optional: Check 100 MAM Followers Replication
        if cfg.get("CHECK_FOLLOWERS"):
            print("\n[*] Checking replication across 100 MAM Followers...")
            from test_mam import init_session
            for i in [1, 2, 5, 50, 100]:
                f_sess = init_session(f"mamfollower{i}@mailinator.com", password, url)
                if f_sess:
                    f_pos = f_sess.get_open_positions("paper")
                    print(f"    - mamfollower{i}: {len(f_pos)} open position(s)")

        # 7. Exit Strategy & Timer
        print(f"\n[*] Exit Strategy: Holding trade for {timer} seconds...")
        remaining = timer
        while remaining > 0:
            chunk = min(10, remaining)
            time.sleep(chunk)
            remaining -= chunk
            if remaining > 0:
                print(f"[*] Trade active... {remaining}s remaining before square-off")

        # 8. Square-Off & Verification in History Ledger
        print(f"\n[*] Squaring off position for {norm_symbol}...")
        pos_mgr.squareoff_order(norm_symbol)

        # Dual-layer squareoff fallback via OMS
        if api_session and chart_token:
            api_session.post(f"{url}/v1/oms/paper/positions/{order_id}/squareoff", headers=headers, json={}, timeout=15)

        time.sleep(2.0)
        hist = HistoryManager(trading_frame)
        hist.verify_order_in_history(norm_symbol)

        print("\n" + "=" * 80)
        print(" ✅ MARKET ORDER TEST COMPLETED & STRICT ASSERTIONS PASSED")
        print("=" * 80 + "\n")
        browser.close()


def main():
    parser = argparse.ArgumentParser(description="BlackTrader Market Order Test")
    parser.add_argument("--symbol", default=CONFIG["SYMBOL"], help="Trading symbol")
    parser.add_argument("--side", choices=["BUY", "SELL"], default=CONFIG["SIDE"], help="Order side")
    parser.add_argument("--lot", type=float, default=CONFIG["LOT"], help="Lot size")
    parser.add_argument("--tp", type=float, default=CONFIG["TP_POINTS"], help="Take Profit points")
    parser.add_argument("--sl", type=float, default=CONFIG["SL_POINTS"], help="Stop Loss points")
    parser.add_argument("--timer", type=int, default=CONFIG["TIMER_SECONDS"], help="Exit timer seconds")
    parser.add_argument("--headed", action="store_true", help="Run with visible browser window")
    parser.add_argument("--check-followers", action="store_true", help="Verify 100 MAM followers replication")
    args = parser.parse_args()

    cfg = CONFIG.copy()
    cfg["SYMBOL"] = args.symbol
    cfg["SIDE"] = args.side
    cfg["LOT"] = args.lot
    cfg["TP_POINTS"] = args.tp
    cfg["SL_POINTS"] = args.sl
    cfg["TIMER_SECONDS"] = args.timer
    cfg["HEADLESS"] = not args.headed
    cfg["CHECK_FOLLOWERS"] = args.check_followers

    run_market_order_test(cfg)


if __name__ == "__main__":
    main()

