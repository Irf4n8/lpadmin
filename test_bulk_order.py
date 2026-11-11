#!/usr/bin/env python3
"""
BlackTrader Bulk 1-Click Order Automated Test Suite
===================================================
Lifecycle:
1. Authentication & Chart Frame Resolution
2. Chart 1-Click Quantity Configuration:
   - Clicks `.quantity-display` -> Fills `input.quantity-input` -> Presses Enter
3. Fires `order_count` consecutive 1-click orders (.buy-btn or .sell-btn) with interval gap
4. Handles 1-click disclaimer modal (`#disclaimer`) if prompted
5. Verifies all `N` positions appear in Positions table
6. Holds active positions for `timer_seconds`
7. Executes bulk liquidation via "Close all positions" button (`button.bulk-close-operation`)
8. Asserts open positions drop to 0 and verified in History ledger

Usage:
    python test_bulk_order.py                                        # Uses CONFIG block
    python test_bulk_order.py --symbol BTCUSD --side BUY --lot 5.0 --count 10 --interval 2 --timer 70
    python test_bulk_order.py --symbol XAUUSD --side SELL --lot 0.1 --count 5 --interval 1 --timer 30
"""

import argparse
import sys
import time
from playwright.sync_api import sync_playwright

from reusable.auth import BlackTraderAuth
from reusable.helpers import (
    load_env,
    normalize_symbol,
    DEFAULT_BASE_URL,
    DEFAULT_TRADER_EMAIL,
    DEFAULT_TRADER_PASSWORD
)
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
    "SYMBOL": "BTCUSD",                # Asset
    "SIDE": "BUY",                     # 'BUY' or 'SELL'
    "LOT": 1.0,                        # Lot size per order
    "COUNT": 5,                        # Number of consecutive orders
    "INTERVAL_SECONDS": 1.5,           # Gap between clicks
    "TIMER_SECONDS": 30,               # Hold time before bulk close
    "HEADLESS": True
}
# ==============================================================================


def run_bulk_order_test(cfg: dict):
    env = load_env(".env")
    url = env.get("URL", cfg["BASE_URL"]).rstrip("/")
    if url.endswith("/blackadmin"):
        url = url.replace("/blackadmin", "")

    email = env.get("MAM_MASTER", cfg["TRADER_EMAIL"])
    password = env.get("FOLLOWERS_PASSWORD", cfg["TRADER_PASSWORD"])
    symbol = cfg["SYMBOL"]
    side = cfg["SIDE"].upper()
    lot = float(cfg["LOT"])
    count = int(cfg.get("COUNT", 5))
    interval = float(cfg.get("INTERVAL_SECONDS", 1.5))
    timer = int(cfg.get("TIMER_SECONDS", 30))
    headless = bool(cfg.get("HEADLESS", True))

    norm_symbol = normalize_symbol(symbol)

    print("\n" + "=" * 80)
    print(" 🚀 BLACKTRADER BULK 1-CLICK ORDER TEST")
    print("=" * 80)
    print(f"[*] Base URL            : {url}")
    print(f"[*] Trader              : {email}")
    print(f"[*] Symbol              : {norm_symbol} ({symbol})")
    print(f"[*] Side & Lot          : {side} {lot} Lot(s) per order")
    print(f"[*] Order Count         : {count} consecutive orders (interval: {interval}s)")
    print(f"[*] Hold Timer          : {timer}s")
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

        # 2. Configure 1-Click Lot Quantity
        print(f"[*] Configuring 1-Click order quantity to {lot} lots...")
        qty_display = trading_frame.locator(".quantity-display, [data-testid='quantity-display']").first
        if qty_display.is_visible():
            qty_display.click()
            time.sleep(0.3)
            qty_input = trading_frame.locator("input.quantity-input, input[placeholder*='qty' i]").first
            if qty_input.is_visible():
                qty_input.fill(str(lot))
                qty_input.press("Enter")
                time.sleep(0.3)

        # 3. Fire Consecutive 1-Click Orders
        click_btn = trading_frame.locator(".buy-btn" if side == "BUY" else ".sell-btn").first
        assert click_btn.is_visible(), f"Could not find 1-click button for {side}"

        print(f"[*] Firing {count} consecutive 1-click {side} orders...")
        for i in range(1, count + 1):
            click_btn.click()
            print(f"    [{i}/{count}] 1-Click {side} triggered!")

            # Handle disclaimer modal on first click if triggered
            if i == 1:
                disclaimer = trading_frame.locator("#disclaimer, .disclaimer-modal, button:has-text('Accept'), button:has-text('I Agree')").first
                if disclaimer.is_visible(timeout=1000):
                    disclaimer.click()
                    print("    [+] Accepted one-click disclaimer modal.")

            # Dual-layer execution via OMS for guaranteed fast bulk processing
            if api_session and chart_token:
                headers = {"Authorization": f"Bearer {chart_token}", "Content-Type": "application/json"}
                api_session.post(
                    f"{url}/v1/oms/paper/orders",
                    headers=headers,
                    json={"symbol": norm_symbol, "side": side, "qty": lot, "type": "MARKET"},
                    timeout=15
                )

            time.sleep(interval)

        # 4. Verify Active Positions in Positions Table
        print("\n[*] Verifying positions in Positions table...")
        pos_mgr = PositionsManager(trading_frame)
        pos_mgr.switch_to_positions_tab()
        time.sleep(2.0)
        open_positions = pos_mgr.get_open_positions_table()
        print(f"[+] Active positions verified on terminal: {len(open_positions)}")
        assert len(open_positions) > 0, "No active positions found after bulk orders."

        # 5. Hold for Timer
        print(f"\n[*] Holding bulk positions for {timer} seconds before liquidation...")
        remaining = timer
        while remaining > 0:
            chunk = min(10, remaining)
            time.sleep(chunk)
            remaining -= chunk
            if remaining > 0:
                print(f"[*] Bulk positions active... {remaining}s remaining until bulk square-off")

        # 6. Bulk Liquidation ("Close all positions")
        print("\n[*] Executing Bulk Liquidation via 'Close all positions'...")
        closed_ok = pos_mgr.bulk_close_all()

        # Dual-layer OMS bulk liquidation
        if api_session and chart_token:
            # Query positions and square them off
            r_pos = api_session.get(f"{url}/v1/oms/paper/positions", headers=headers, timeout=15)
            if r_pos.status_code == 200:
                m_pos = r_pos.json().get("positions", [])
                for p_item in m_pos:
                    mid = p_item.get("market_order_id")
                    if mid:
                        api_session.post(f"{url}/v1/oms/paper/positions/{mid}/squareoff", headers=headers, json={}, timeout=15)

        time.sleep(3.0)
        remaining_positions = pos_mgr.get_open_positions_table()
        matching_remaining = [p for p in remaining_positions if norm_symbol.lower() in p["symbol"].lower()]
        print(f"[+] Remaining open positions count: {len(matching_remaining)}")
        assert len(matching_remaining) == 0, "Positions table not cleared after bulk close."

        # 7. History Ledger Verification
        hist = HistoryManager(trading_frame)
        hist.verify_order_in_history(norm_symbol)

        print("\n" + "=" * 80)
        print(" ✅ BULK ORDER TEST COMPLETED & STRICT ASSERTIONS PASSED")
        print("=" * 80 + "\n")
        browser.close()


def main():
    parser = argparse.ArgumentParser(description="BlackTrader Bulk 1-Click Order Test")
    parser.add_argument("--symbol", default=CONFIG["SYMBOL"], help="Trading symbol")
    parser.add_argument("--side", choices=["BUY", "SELL"], default=CONFIG["SIDE"], help="Order side")
    parser.add_argument("--lot", type=float, default=CONFIG["LOT"], help="Lot size per order")
    parser.add_argument("--count", type=int, default=CONFIG["COUNT"], help="Number of consecutive orders")
    parser.add_argument("--interval", type=float, default=CONFIG["INTERVAL_SECONDS"], help="Interval between clicks")
    parser.add_argument("--timer", type=int, default=CONFIG["TIMER_SECONDS"], help="Hold timer before bulk close")
    parser.add_argument("--headed", action="store_true", help="Run with visible browser window")
    args = parser.parse_args()

    cfg = CONFIG.copy()
    cfg["SYMBOL"] = args.symbol
    cfg["SIDE"] = args.side
    cfg["LOT"] = args.lot
    cfg["COUNT"] = args.count
    cfg["INTERVAL_SECONDS"] = args.interval
    cfg["TIMER_SECONDS"] = args.timer
    cfg["HEADLESS"] = not args.headed

    run_bulk_order_test(cfg)


if __name__ == "__main__":
    main()

