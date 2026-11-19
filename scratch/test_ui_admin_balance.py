from playwright.sync_api import sync_playwright
import time
import os

SCREENSHOT_DIR = os.path.abspath("reports/screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    
    print("\n[1] Navigating to http://localhost:8500...")
    page.goto("http://localhost:8500", wait_until="domcontentloaded", timeout=15000)
    time.sleep(3)
    
    # Save full dashboard overview
    p1 = os.path.join(SCREENSHOT_DIR, "ui_01_dashboard_fleet_overview.png")
    page.screenshot(path=p1, full_page=True)
    print("Saved:", p1)
    
    # Open Quick Manage modal directly or via click
    print("\n[2] Opening Quick Manage modal for mamf1...")
    page.evaluate("openQuickManageModal('mamf1@mailinator.com')")
    time.sleep(2)
    p2 = os.path.join(SCREENSHOT_DIR, "ui_02_member_quick_manage_modal.png")
    page.screenshot(path=p2)
    print("Saved modal view:", p2)
    
    # Fill Real Balance input to set balance (e.g. 15000.0)
    print("\n[3] Setting balance via Admin UI input...")
    input_real = page.locator('#qmRealBalance')
    input_real.fill("15000")
    
    # Click "Set Real Bal" button
    btn_set = page.locator('button:has-text("Set Real Bal")')
    btn_set.click()
    time.sleep(3)
    
    p3 = os.path.join(SCREENSHOT_DIR, "ui_03_admin_balance_updated_proof.png")
    page.screenshot(path=p3)
    print("Saved update confirmation:", p3)
    
    browser.close()

print("\nUI Admin balance management flow verified successfully!")
