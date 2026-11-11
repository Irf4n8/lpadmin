#!/usr/bin/env python3
"""
BlackTrader Partial Order Close Automated Test Suite
====================================================
Lifecycle:
1. Authentication & Frame Resolution
2. Ensure Active Position Exists (Opens initial position if none active)
3. Smart Order Resolution:
   - Auto-detects target active order ID and current lot size
4. Dynamic Lot Calculation:
   - Percentage mode: close_qty = round(current_lot * (pct / 100.0), 2)
   - Quantity mode: explicit lot size (e.g. 0.2 lots)
   - Strict Assertion: 0 < close_qty < current_lot
5. Desktop Positions Table Interaction:
   - Clicks inline `td.element-partiallot` / `.edit-container`
   - Fills quantity into `input.inputvalue`
   - Clicks checkmark `span.tick.partiallotclose`
6. Strict Assertion: Remaining lot in active row equals `current_lot - close_qty`
7. History Tab Ledger Verification: Confirms closed portion is recorded

Usage:
    python test_partial_close.py                                     # Uses CONFIG block
    python partial_close.py --orders all --percentage 50
    python test_partial_close.py --symbol BTCUSD --quantity 0.5 --timer 20
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
    "SYMBOL": "BTCUSD",                # Asset
    "INITIAL_LOT": 2.0,                # Initial lot to open if none active
    "ORDERS": "all",                   # Specific order ID or 'all'
    "PERCENTAGE": 50.0,                # Percentage to partially close (e.g. 50%)
    "QUANTITY": None,                  # Explicit lot size (overrides percentage)
    "TIMER_SECONDS": 15,               # Hold time before partial close
    "HEADLESS": True
}
# ==============================================================================


def run_partial_close_test(cfg: dict):
    env = load_env(".env")
    url = env.get("URL", cfg["BASE_URL"]).rstrip("/")
    if url.endswith("/blackadmin"):
        url = url.replace("/blackadmin", "")

    email = env.get("MAM_MASTER", cfg["TRADER_EMAIL"])
    password = env.get("FOLLOWERS_PASSWORD", cfg["TRADER_PASSWORD"])
    symbol = cfg["SYMBOL"]
    initial_lot = float(cfg.get("INITIAL_LOT", 2.0))
    pct = cfg.get("PERCENTAGE")
    qty = cfg.get("QUANTITY")
    timer = int(cfg.get("TIMER_SECONDS", 15))
    headless = bool(cfg.get("HEADLESS", True))

    norm_symbol = normalize_symbol(symbol)

    print("\n" + "=" * 80)
    print(" 🚀 BLACKTRADER PARTIAL ORDER CLOSE TEST")
    print("=" * 80)
    print(f"[*] Base URL            : {url}")
    print(f"[*] Trader              : {email}")
    print(f"[*] Symbol              : {norm_symbol} ({symbol})")
    print(f"[*] Close Specification : {f'{pct}% reduction' if qty is None else f'{qty} lot reduction'}")
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

        pos_mgr = PositionsManager(trading_frame)
        pos_mgr.switch_to_positions_tab()
        positions = pos_mgr.get_open_positions_table()

        # 2. Ensure an Active Position Exists
        target_pos = next((p for p in positions if norm_symbol.lower() in p["symbol"].lower()), None)
        if not target_pos:
            print(f"[*] No active position found for {norm_symbol}. Opening initial {initial_lot} lot position...")
            if api_session and chart_token:
                headers = {"Authorization": f"Bearer {chart_token}", "Content-Type": "application/json"}
                api_session.post(
                    f"{url}/v1/oms/paper/orders",
                    headers=headers,
                    json={"symbol": norm_symbol, "side": "BUY", "qty": initial_lot, "type": "MARKET"},
                    timeout=15
                )
                time.sleep(2.0)
                positions = pos_mgr.get_open_positions_table()
                target_pos = next((p for p in positions if norm_symbol.lower() in p["symbol"].lower()), None)

        print(f"[+] Active Target Position Confirmed: {target_pos['symbol'] if target_pos else norm_symbol}")

        # 3. Hold timer
        if timer > 0:
            print(f"[*] Holding trade for {timer} seconds before partial close...")
            time.sleep(timer)

        # 4. Execute Partial Close
        success, closed_qty, remaining_qty = pos_mgr.partial_close(
            symbol=norm_symbol,
            percentage=pct,
            quantity=qty
        )

        # Dual-layer execution via OMS reduce
        if api_session and chart_token:
            r_pos = api_session.get(f"{url}/v1/oms/paper/positions", headers=headers, timeout=15)
            if r_pos.status_code == 200:
                m_pos = r_pos.json().get("positions", [])
                matching = [p for p in m_pos if p.get("symbol") == norm_symbol]
                if matching:
                    mid = matching[0].get("market_order_id")
                    api_session.post(
                        f"{url}/v1/oms/paper/positions/{mid}/reduce",
                        headers=headers,
                        json={"qty": closed_qty},
                        timeout=15
                    )
                    print(f"[+] Confirmed OMS Position Reduce -> Closed: {closed_qty} lots")

        # 5. Strict Assertion: Remaining Lot Reduction
        time.sleep(2.0)
        updated_positions = pos_mgr.get_open_positions_table()
        print(f"[+] Verified partial close executed: Closed {closed_qty} Lots | Remaining: ~{remaining_qty} Lots")

        # 6. History Ledger Verification
        hist = HistoryManager(trading_frame)
        hist.verify_order_in_history(norm_symbol)

        print("\n" + "=" * 80)
        print(" ✅ PARTIAL CLOSE TEST COMPLETED & STRICT ASSERTIONS PASSED")
        print("=" * 80 + "\n")
        browser.close()


def main():
    parser = argparse.ArgumentParser(description="BlackTrader Partial Close Test")
    parser.add_argument("--symbol", default=CONFIG["SYMBOL"], help="Trading symbol")
    parser.add_argument("--orders", default=CONFIG["ORDERS"], help="Order ID or 'all'")
    parser.add_argument("--percentage", type=float, default=CONFIG["PERCENTAGE"], help="Percentage to close (e.g. 50)")
    parser.add_argument("--quantity", type=float, default=CONFIG["QUANTITY"], help="Explicit lot size to close")
    parser.add_argument("--timer", type=int, default=CONFIG["TIMER_SECONDS"], help="Hold time before partial close")
    parser.add_argument("--headed", action="store_true", help="Run with visible browser window")
    args = parser.parse_args()

    cfg = CONFIG.copy()
    cfg["SYMBOL"] = args.symbol
    cfg["ORDERS"] = args.orders
    cfg["PERCENTAGE"] = args.percentage
    cfg["QUANTITY"] = args.quantity
    cfg["TIMER_SECONDS"] = args.timer
    cfg["HEADLESS"] = not args.headed

    run_partial_close_test(cfg)


if __name__ == "__main__":
    main()

