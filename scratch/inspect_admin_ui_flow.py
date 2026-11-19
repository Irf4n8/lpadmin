from playwright.sync_api import sync_playwright
import time
import os

os.makedirs("reports/screenshots", exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    
    print("Navigating to login...")
    page.goto("https://lpadmin.blackfx.com/login", wait_until="networkidle")
    page.fill('input[name="email"]', "lpadmin@blacktrader.com")
    page.fill('input[name="password"]', "Raj1234!")
    page.click('button[type="submit"]')
    time.sleep(4)
    
    print("Current URL:", page.url)
    page.screenshot(path="reports/screenshots/admin_post_login.png", full_page=True)
    
    # Print all interactive links & buttons
    links = page.query_selector_all("a, button, nav")
    for el in links:
        href = el.get_attribute("href") or ""
        txt = el.inner_text().strip()
        if txt or href:
            print(f"Element: [{txt}] -> {href}")

    # Check /members or /admin/members or search for member in page
    print("\nAttempting navigation to /members...")
    page.goto("https://lpadmin.blackfx.com/members", wait_until="networkidle")
    time.sleep(2)
    print("URL after /members:", page.url)
    page.screenshot(path="reports/screenshots/page_members.png", full_page=True)

    print("\nAttempting navigation to /admin...")
    page.goto("https://lpadmin.blackfx.com/admin", wait_until="networkidle")
    time.sleep(2)
    print("URL after /admin:", page.url)
    page.screenshot(path="reports/screenshots/page_admin.png", full_page=True)

    browser.close()
