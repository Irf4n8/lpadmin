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
    
    print("\n[2] Clicking on MEMBERS tab/card...")
    # Click on the card or link with "MEMBERS"
    members_btn = page.locator('text=MEMBERS').first
    members_btn.click()
    time.sleep(4)
    
    print("URL on members page:", page.url)
    p_members = os.path.join(SCREENSHOT_DIR, "03_blackadmin_members_list.png")
    page.screenshot(path=p_members, full_page=True)
    print("Saved members list screenshot:", p_members)
    
    # Search for mamf1 in search input if present
    print("\n[3] Searching for mamf1@mailinator.com...")
    search_inp = page.locator('input[type="search"], input[placeholder*="Search"], input[type="text"]')
    if search_inp.count() > 0:
        search_inp.first.fill("mamf1@mailinator.com")
        time.sleep(3)
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "04_blackadmin_members_search.png"))
        
    # Click on mamf1 member row/link
    print("\n[4] Clicking on member mamf1...")
    mem_link = page.locator('text=mamf1@mailinator.com').first
    if mem_link.count() > 0:
        mem_link.click()
    else:
        # Click first row/link in table
        page.locator('tbody tr, a[href*="member"]').first.click()
        
    time.sleep(4)
    print("URL on member profile:", page.url)
    p_profile = os.path.join(SCREENSHOT_DIR, "05_blackadmin_member_profile.png")
    page.screenshot(path=p_profile, full_page=True)
    print("Saved member profile screenshot:", p_profile)
    
    # Check buttons and elements on member profile
    buttons = page.query_selector_all("button, a, input")
    print("\nActions on member profile:")
    for b in buttons:
        txt = b.inner_text().strip()
        val = b.get_attribute("value") or ""
        placeholder = b.get_attribute("placeholder") or ""
        if txt or val or placeholder:
            print(f"  Element: [{txt}] val: [{val}] placeholder: [{placeholder}]")
            
    browser.close()

print("\nBlackadmin member profile inspection finished.")
