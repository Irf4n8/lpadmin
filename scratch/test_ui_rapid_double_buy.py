from playwright.sync_api import sync_playwright
import time
import os

SCREENSHOT_DIR = os.path.abspath("reports/screenshots/race_ui")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    page = context.new_page()
    
    print("[1] Logging into BlackTrader as Master (mamm@mailinator.com)...")
    page.goto("https://lpadmin.blackfx.com/login", wait_until="networkidle")
    page.fill('input[type="email"], input[name="email"]', "mamm@mailinator.com")
    page.fill('input[type="password"], input[name="password"]', "12345678")
    page.click('button[type="submit"]')
    page.wait_for_timeout(3000)
    
    print("[2] Navigating to BlackTrader Trading Terminal (/dashboard)...")
    page.goto("https://lpadmin.blackfx.com/dashboard", wait_until="networkidle")
    page.wait_for_timeout(6000)
    
    # Locate chart frame
    chart_frame = None
    for f in page.frames:
        if "chartv2.blacktrader.com" in f.url:
            chart_frame = f
            break
            
    if not chart_frame:
        print("ERROR: Chart frame not found!")
        browser.close()
        exit(1)
        
    print("Found Chart Frame:", chart_frame.url[:60])
    
    # Take screenshot before order
    p_before = os.path.join(SCREENSHOT_DIR, "ui_net01_01_terminal_before_buy.png")
    page.screenshot(path=p_before)
    print("Saved:", p_before)
    
    # In chart frame, look for BUY button
    # In earlier dump: Btn: 'B' cls='a b svelte-1jzfxp' (BUY button)
    buy_btn = chart_frame.locator('button.a.b, button:has-text("B"), button:has-text("BUY")').first
    print("Buy button text:", buy_btn.inner_text().strip())
    
    # Check if quantity input is present and set to 0.001
    qty_input = chart_frame.locator('input[type="number"].av-in, input.av-in').first
    if qty_input.count() > 0:
        print("Setting quantity to 0.001...")
        qty_input.fill("0.001")
        
    # Simulate Rapid Double Click (Race NET01)
    print("[3] Simulating Rapid Double Click on BUY button...")
    buy_btn.click()
    # Click again immediately (within 50ms)
    buy_btn.click()
    page.wait_for_timeout(4000)
    
    # Take screenshot after double click
    p_after = os.path.join(SCREENSHOT_DIR, "ui_net01_02_terminal_after_double_buy.png")
    page.screenshot(path=p_after)
    print("Saved:", p_after)
    
    browser.close()

# Verify orders created in OMS API
import requests
s_m = requests.Session()
s_m.post("https://lpadmin.blackfx.com/api/auth/login", json={"email": "mamm@mailinator.com", "password": "12345678"})
t_m = s_m.post("https://lpadmin.blackfx.com/api/auth/chart-token").json().get("token")
h_m = {"Authorization": f"Bearer {t_m}", "Content-Type": "application/json"}

pos_m = s_m.get("https://lpadmin.blackfx.com/v1/oms/real/positions", headers=h_m).json().get("positions", [])
print(f"\n[4] Master Open Positions Result: {len(pos_m)}")
for p in pos_m:
    print(f"  Pos ID: {p.get('position_id')}, Qty: {p.get('net_qty')}, Margin: {p.get('margin_used')}")
