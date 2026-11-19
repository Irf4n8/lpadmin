from playwright.sync_api import sync_playwright
import time
import os

SCREENSHOT_DIR = os.path.abspath("reports/screenshots/blackadmin")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    
    print("\n[1] Logging into https://lpadmin.blackfx.com/blackadmin...")
    page.goto("https://lpadmin.blackfx.com/blackadmin", wait_until="networkidle")
    time.sleep(2)
    
    page.fill('input[type="email"], input[name="email"]', "lpadmin@blacktrader.com")
    page.fill('input[type="password"], input[name="password"]', "Raj1234!")
    page.click('button[type="submit"]')
    time.sleep(4)
    
    print("\n[2] Clicking on Members...")
    # Click text=Members
    page.locator('text=Members').first.click()
    time.sleep(3)
    
    print("\n[3] Searching for mamf1@mailinator.com...")
    search_inp = page.locator('input[placeholder*="email, name or user id"]')
    search_inp.fill("mamf1@mailinator.com")
    time.sleep(3)
    
    page.screenshot(path=os.path.join(SCREENSHOT_DIR, "04_blackadmin_filtered_members.png"))
    print("Saved filtered members table screenshot.")
    
    # Click the row
    print("\n[4] Clicking member row...")
    row = page.locator('tr:has-text("mamf1@mailinator.com"), div:has-text("mamf1@mailinator.com")').last
    row.click()
    time.sleep(4)
    
    page.screenshot(path=os.path.join(SCREENSHOT_DIR, "05_blackadmin_member_drawer_profile.png"), full_page=True)
    print("Saved member profile drawer screenshot.")
    
    # Check all interactive elements on profile drawer
    all_elements = page.query_selector_all("button, input, [role='button'], a")
    print("\nElements in member detail view:")
    for el in all_elements:
        t = el.inner_text().strip().replace('\n', ' ')
        p = el.get_attribute("placeholder") or ""
        val = el.get_attribute("value") or ""
        if t or p or val:
            print(f"  [{t}] placeholder:[{p}] value:[{val}]")
            
    browser.close()

print("\nFinished inspecting member drawer.")
