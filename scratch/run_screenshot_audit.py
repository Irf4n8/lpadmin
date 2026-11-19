import os
import time
from playwright.sync_api import sync_playwright

BASE_URL = "https://lpadmin.blackfx.com"
SCREENSHOT_DIR = os.path.abspath("reports/screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    
    # 1. Capture Master mamm UI (Negative Balance -$100,243.91)
    print("\n[1] Logging in as Master (mamm@mailinator.com)...")
    context_m = browser.new_context(viewport={"width": 1440, "height": 900})
    page_m = context_m.new_page()
    page_m.goto(f"{BASE_URL}/login")
    page_m.fill('input[name="email"]', "mamm@mailinator.com")
    page_m.fill('input[name="password"]', "12345678")
    page_m.click('button[type="submit"]')
    time.sleep(4)
    print("Master Logged in. URL:", page_m.url)
    img_m = os.path.join(SCREENSHOT_DIR, "01_master_negative_balance_ui.png")
    page_m.screenshot(path=img_m, full_page=True)
    print("Saved:", img_m)

    # 2. Capture Admin Portal (Admin managing members & balances)
    print("\n[2] Logging in as Admin (lpadmin@blacktrader.com)...")
    context_a = browser.new_context(viewport={"width": 1440, "height": 900})
    page_a = context_a.new_page()
    page_a.goto(f"{BASE_URL}/login")
    page_a.fill('input[name="email"]', "lpadmin@blacktrader.com")
    page_a.fill('input[name="password"]', "Raj1234!")
    page_a.click('button[type="submit"]')
    time.sleep(4)
    print("Admin Logged in. URL:", page_a.url)
    img_a = os.path.join(SCREENSHOT_DIR, "02_admin_dashboard_ui.png")
    page_a.screenshot(path=img_a, full_page=True)
    print("Saved:", img_a)

    # If admin has member view or admin tab, navigate there
    try:
        # Check links
        admin_links = page_a.query_selector_all('a[href*="admin"], a[href*="member"]')
        print("Admin navigation links:", [a.get_attribute("href") for a in admin_links])
        if admin_links:
            page_a.goto(f"{BASE_URL}" + admin_links[0].get_attribute("href"))
            time.sleep(3)
            img_a2 = os.path.join(SCREENSHOT_DIR, "03_admin_members_ledger_ui.png")
            page_a.screenshot(path=img_a2, full_page=True)
            print("Saved:", img_a2)
    except Exception as e:
        print("Admin subnavigation note:", e)

    # 3. Capture Follower 1 (mamf1@mailinator.com)
    print("\n[3] Logging in as Follower 1 (mamf1@mailinator.com)...")
    context_f = browser.new_context(viewport={"width": 1440, "height": 900})
    page_f = context_f.new_page()
    page_f.goto(f"{BASE_URL}/login")
    page_f.fill('input[name="email"]', "mamf1@mailinator.com")
    page_f.fill('input[name="password"]', "12345678")
    page_f.click('button[type="submit"]')
    time.sleep(4)
    print("Follower 1 Logged in. URL:", page_f.url)
    img_f = os.path.join(SCREENSHOT_DIR, "04_follower_1_dashboard_ui.png")
    page_f.screenshot(path=img_f, full_page=True)
    print("Saved:", img_f)

    # 4. Capture Follower 1 Copy / MAM tab if available
    try:
        mam_links = page_f.query_selector_all('a[href*="mam"], a[href*="copy"], a[href*="manager"]')
        print("Follower MAM/Copy links:", [a.get_attribute("href") for a in mam_links])
        if mam_links:
            page_f.goto(f"{BASE_URL}" + mam_links[0].get_attribute("href"))
            time.sleep(3)
            img_f2 = os.path.join(SCREENSHOT_DIR, "05_follower_mam_active_3_followers_ui.png")
            page_f.screenshot(path=img_f2, full_page=True)
            print("Saved:", img_f2)
    except Exception as e:
        print("Follower subnavigation note:", e)

    browser.close()

print("\nScreenshot generation completed successfully!")
