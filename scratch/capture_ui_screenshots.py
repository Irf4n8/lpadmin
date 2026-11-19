import os
import time
from playwright.sync_api import sync_playwright

BASE_URL = "https://lpadmin.blackfx.com"
SCREENSHOT_DIR = os.path.abspath("reports/screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

print(f"Capturing screenshots to: {SCREENSHOT_DIR}")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()

    # 1. Login as Master (mamm@mailinator.com) - Shows Negative Balance
    print("\n[1] Capturing Master Account with Negative Balance...")
    page.goto(f"{BASE_URL}")
    time.sleep(2)
    
    # Check if login form exists
    try:
        # Fill trader login
        page.fill('input[type="email"], input[name="email"]', "mamm@mailinator.com")
        page.fill('input[type="password"], input[name="password"]', "12345678")
        page.click('button[type="submit"]')
        time.sleep(3)
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "01_master_negative_balance_dashboard.png"), full_page=True)
        print(" -> Saved 01_master_negative_balance_dashboard.png")
    except Exception as e:
        print(" -> Master login capture error:", e)

    # 2. Login as Admin to capture Member Management & Negative Balance
    print("\n[2] Capturing Admin Portal with Member Negative Balance...")
    page.goto(f"{BASE_URL}/admin")
    time.sleep(2)
    try:
        page.fill('input[type="email"], input[name="email"]', "lpadmin@blacktrader.com")
        page.fill('input[type="password"], input[name="password"]', "Raj1234!")
        page.click('button[type="submit"]')
        time.sleep(3)
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "02_admin_portal_overview.png"), full_page=True)
        print(" -> Saved 02_admin_portal_overview.png")
        
        # Navigate to members if possible
        page.goto(f"{BASE_URL}/admin/members")
        time.sleep(3)
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "03_admin_members_negative_balance.png"), full_page=True)
        print(" -> Saved 03_admin_members_negative_balance.png")
    except Exception as e:
        print(" -> Admin capture error:", e)

    # 3. Login as Follower 1 (mamf1@mailinator.com)
    print("\n[3] Capturing Follower 1 Dashboard...")
    page.goto(f"{BASE_URL}")
    time.sleep(2)
    try:
        page.fill('input[type="email"], input[name="email"]', "mamf1@mailinator.com")
        page.fill('input[type="password"], input[name="password"]', "12345678")
        page.click('button[type="submit"]')
        time.sleep(3)
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "04_follower_1_dashboard.png"), full_page=True)
        print(" -> Saved 04_follower_1_dashboard.png")
    except Exception as e:
        print(" -> Follower 1 capture error:", e)

    browser.close()

print("Screenshot capture finished!")
