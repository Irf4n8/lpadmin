from playwright.sync_api import sync_playwright
import time
import os

SCREENSHOT_DIR = os.path.abspath("reports/screenshots/blackadmin")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    
    print("\n[1] Navigating to https://lpadmin.blackfx.com/blackadmin...")
    page.goto("https://lpadmin.blackfx.com/blackadmin", wait_until="networkidle")
    time.sleep(3)
    
    print("URL:", page.url)
    p_login = os.path.join(SCREENSHOT_DIR, "01_blackadmin_login_page.png")
    page.screenshot(path=p_login)
    print("Saved login page:", p_login)
    
    # Check inputs on login page
    inputs = page.query_selector_all("input")
    print("Inputs on page:", [i.get_attribute("type") or i.get_attribute("name") for i in inputs])
    
    # Fill admin login
    email_inp = page.locator('input[type="email"], input[name="email"]')
    pwd_inp = page.locator('input[type="password"], input[name="password"]')
    
    if email_inp.count() > 0:
        email_inp.fill("lpadmin@blacktrader.com")
        pwd_inp.fill("Raj1234!")
        page.click('button[type="submit"]')
        time.sleep(5)
        
    print("URL after login:", page.url)
    p_dash = os.path.join(SCREENSHOT_DIR, "02_blackadmin_after_login.png")
    page.screenshot(path=p_dash, full_page=True)
    print("Saved post-login dashboard:", p_dash)
    
    # Find links on admin page (e.g. Members)
    links = page.query_selector_all("a, button, nav")
    print("\nAdmin navigation items:")
    for el in links:
        txt = el.inner_text().strip()
        href = el.get_attribute("href") or ""
        if txt or href:
            print(f"  [{txt}] -> {href}")
            
    browser.close()

print("\nBlackadmin inspection script finished.")
