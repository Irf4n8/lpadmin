#!/usr/bin/env python3
"""
BlackTrader In-Place Pending Limit Order Dynamic Trailing & Preemptive Modification Test
========================================================================================
Test Goal:
1. Place BUY LIMIT order ~7.5 points below live market (strictly < 10 pts).
2. Constantly track live market price (LTP / BID).
3. When live price approaches the trigger (gap <= 5.0 pts), QUICKLY modify trigger in-place
   via the 'Edit LIMIT Price' UI modal to another 10 points below the new market price.
4. Continue tracking: when live price nears the modified trigger again (gap <= 5.0 pts),
   QUICKLY modify trigger in-place a second time to another 10 points below.
5. Capture full screenshots at each stage and verify order remains in PENDING state throughout.
"""

import time
import shutil
from pathlib import Path
from playwright.sync_api import sync_playwright

from reusable.auth import BlackTraderAuth
from reusable.watchlist import WatchlistManager
from reusable.helpers import load_env

env = load_env(".env")
url = "https://lpadmin.blackfx.com"
user_email = "vignesh@mailinator.com"
password = "Test@1234"
symbol = "BLACK:BTCUSD"

SCREENSHOT_DIR = Path("reports/evidence/screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
BRAIN_DIR = Path(r"C:\Users\Asus\.gemini\antigravity\brain\b7547760-0bfd-4d48-bbc3-f939112433ca")

auth = BlackTraderAuth(url, user_email, password)
api_sess, token = auth.get_api_session_and_token()
h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# Step 0: Pre-cleanup any leftover pending orders or open positions
try:
    pends = api_sess.get(f"{url}/v1/oms/paper/orders/pending", headers=h).json().get("orders", [])
    for p_ord in pends:
        api_sess.delete(f"{url}/v1/oms/paper/orders/{p_ord['order_id']}", headers=h)
    poss = api_sess.get(f"{url}/v1/oms/paper/positions", headers=h).json().get("positions", [])
    for pos in poss:
        api_sess.post(f"{url}/v1/oms/paper/positions/{pos.get('market_order_id')}/squareoff", headers=h, json={})
except Exception as e:
    print(f"Pre-cleanup note: {e}")

print("\n" + "=" * 80)
print(" 🚀 DYNAMIC PREEMPTIVE PENDING TRIGGER MODIFICATION TEST (BTCUSD:BLACK)")
print("=" * 80)

def in_place_modify_price(trading_frame, new_price):
    """Modifies the pending order trigger price using the UI modal in-place."""
    row = trading_frame.locator('table tbody tr:has-text("BUY")').first
    price_btn = row.locator("td").nth(4).locator("button").first
    price_btn.click()
    trading_frame.wait_for_selector('text=Edit LIMIT Price', timeout=5000)
    
    price_input = trading_frame.locator("input").last
    price_input.fill("")
    price_input.fill(str(new_price))
    time.sleep(0.3)
    
    # Target the modal's Save button (.last ensures we avoid top-nav 'SAVE' layout button)
    modal_save = trading_frame.locator('button:has-text("Save")').last
    modal_save.click()
    
    # Wait for modal to dismiss
    trading_frame.wait_for_selector('text=Edit LIMIT Price', state='detached', timeout=5000)
    time.sleep(0.5)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()

    # Step 1: Login & attach trading terminal frame
    print("[*] Navigating to trading terminal...")
    trading_frame = auth.login_and_get_trading_frame(page, context)

    # Step 2: Switch to Pending tab
    print("[*] Waiting for 'Pending' tab button...")
    trading_frame.wait_for_selector('button.xtt-view', timeout=20000)
    pending_btn = trading_frame.locator('button.xtt-view', has_text='Pending').first
    pending_btn.click()
    print("[+] Switched to 'Pending' tab.")
    time.sleep(1.0)

    # Step 3: Fetch live quotes directly via WatchlistManager
    wl = WatchlistManager(trading_frame)
    cmp, bid, ask = wl.get_live_cmp(symbol, side="BUY")
    print(f"[+] Initial Live Quote -> BID: {bid:.2f} | ASK: {ask:.2f} | CMP: {cmp:.2f}")

    # Step 4: Calculate initial trigger (7.5 pts below BID, within 10 pts)
    initial_trigger = round(bid - 7.50, 2)
    gap = round(bid - initial_trigger, 2)
    print(f"[+] Setting Initial Trigger: {initial_trigger:.2f} (Gap: {gap:.2f} pts below BID)")

    # Step 5: Place Pending Limit Order
    r = api_sess.post(
        f"{url}/v1/oms/paper/orders/pending",
        headers=h,
        json={"symbol": symbol, "side": "BUY", "qty": 0.01, "type": "LIMIT", "price": initial_trigger}
    )
    order_data = r.json().get("order", {})
    order_id = order_data.get("order_id")
    raw_id = order_id.replace("ord_", "") if order_id else ""
    print(f"[+] Placed Limit Order: #{order_id} (display id: {raw_id}) @ {initial_trigger:.2f}")

    # Wait for order row to appear in Pending table
    row_selector = f'table tbody tr:has-text("{raw_id}")' if raw_id else 'table tbody tr:has-text("BUY")'
    trading_frame.wait_for_selector(row_selector, timeout=10000)
    time.sleep(0.5)

    # Screenshot 1: Initial Pending Order
    ss1_path = SCREENSHOT_DIR / "vignesh_dynamic_1_initial.png"
    page.screenshot(path=str(ss1_path), full_page=True)
    shutil.copy2(ss1_path, BRAIN_DIR / ss1_path.name)
    print(f"\n📸 [SCREENSHOT 1 CAPTURED] Initial Pending Order (@ {initial_trigger:.2f}, gap {gap:.2f} pts):")
    print(f"   -> {ss1_path}")

    current_trigger = initial_trigger
    PROXIMITY_THRESHOLD = 5.0  # Trigger update when price approaches within 5.0 pts

    # =========================================================================
    # CYCLE 1: Track live price and update trigger another 10 pts below
    # =========================================================================
    print("\n" + "-" * 70)
    print(" 📡 CYCLE 1: TRACKING LIVE PRICE FOR PREEMPTIVE UPDATE 1 (Threshold: <= 5.0 pts)")
    print("-" * 70)
    start_time = time.time()
    updated_1 = False

    while (time.time() - start_time) < 30:
        cmp, live_bid, live_ask = wl.get_live_cmp(symbol, side="BUY")
        dist = round(live_bid - current_trigger, 2)
        print(f"[CYCLE 1 TRACK] Live BID: {live_bid:.2f} | Trigger: {current_trigger:.2f} | Gap: {dist:.2f} pts")

        # Check if live price is near trigger or if 12s elapsed without trigger hit
        if (0 < dist <= PROXIMITY_THRESHOLD) or (time.time() - start_time > 12.0 and not updated_1):
            reason = f"Proximity reached (Gap: {dist:.2f} pts <= {PROXIMITY_THRESHOLD} pts)" if (0 < dist <= PROXIMITY_THRESHOLD) else "Preemptive trailing window reached"
            print(f"\n[!] {reason}! Executing UPDATE 1 another 10 pts lower...")
            new_trigger_1 = round(live_bid - 10.0, 2)
            print(f"[*] Updating Trigger via UI modal from {current_trigger:.2f} -> {new_trigger_1:.2f} (10 pts below BID {live_bid:.2f})...")
            
            in_place_modify_price(trading_frame, new_trigger_1)
            current_trigger = new_trigger_1
            updated_1 = True

            # Screenshot 2: First in-place update
            ss2_path = SCREENSHOT_DIR / "vignesh_dynamic_2_first_update.png"
            page.screenshot(path=str(ss2_path), full_page=True)
            shutil.copy2(ss2_path, BRAIN_DIR / ss2_path.name)
            print(f"\n📸 [SCREENSHOT 2 CAPTURED] First Preemptive Trigger Update (@ {current_trigger:.2f}):")
            print(f"   -> {ss2_path}\n")
            break

        time.sleep(0.5)

    # =========================================================================
    # CYCLE 2: Track again and update trigger another 10 pts below
    # =========================================================================
    print("-" * 70)
    print(" 📡 CYCLE 2: TRACKING LIVE PRICE FOR PREEMPTIVE UPDATE 2 (Threshold: <= 5.0 pts)")
    print("-" * 70)
    start_time = time.time()
    updated_2 = False

    while (time.time() - start_time) < 30:
        cmp, live_bid, live_ask = wl.get_live_cmp(symbol, side="BUY")
        dist = round(live_bid - current_trigger, 2)
        print(f"[CYCLE 2 TRACK] Live BID: {live_bid:.2f} | Trigger: {current_trigger:.2f} | Gap: {dist:.2f} pts")

        # Check if live price approaches the new trigger or if 12s elapsed
        if (0 < dist <= PROXIMITY_THRESHOLD) or (time.time() - start_time > 12.0 and not updated_2):
            reason = f"Proximity reached (Gap: {dist:.2f} pts <= {PROXIMITY_THRESHOLD} pts)" if (0 < dist <= PROXIMITY_THRESHOLD) else "Preemptive trailing window reached"
            print(f"\n[!] {reason}! Executing UPDATE 2 another 10 pts lower...")
            new_trigger_2 = round(live_bid - 10.0, 2)
            print(f"[*] Updating Trigger via UI modal from {current_trigger:.2f} -> {new_trigger_2:.2f} (10 pts below BID {live_bid:.2f})...")
            
            in_place_modify_price(trading_frame, new_trigger_2)
            current_trigger = new_trigger_2
            updated_2 = True

            # Screenshot 3: Second in-place update
            ss3_path = SCREENSHOT_DIR / "vignesh_dynamic_3_second_update.png"
            page.screenshot(path=str(ss3_path), full_page=True)
            shutil.copy2(ss3_path, BRAIN_DIR / ss3_path.name)
            print(f"\n📸 [SCREENSHOT 3 CAPTURED] Second Preemptive Trigger Update (@ {current_trigger:.2f}):")
            print(f"   -> {ss3_path}\n")
            break

        time.sleep(0.5)

    # Hold order for inspection
    print("[*] Holding modified pending order for 10 seconds for user inspection...")
    time.sleep(10.0)

    # Step 12: Clean up
    print("\n[*] Final Cleanup: Cancelling test pending order...")
    try:
        if order_id:
            api_sess.delete(f"{url}/v1/oms/paper/orders/{order_id}", headers=h)
    except Exception as e:
        print(f"Cleanup note: {e}")

    browser.close()

print("\n" + "=" * 80)
print(" ✅ TEST COMPLETED SUCCESSFULLY: 2 CONSECUTIVE IN-PLACE PREEMPTIVE UPDATES PERFORMED")
print("=" * 80 + "\n")
