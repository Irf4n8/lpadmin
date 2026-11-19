from playwright.sync_api import sync_playwright
import time
import os

os.makedirs("reports/screenshots/blackadmin", exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    
    print("[1] Logging in...")
    page.goto("https://lpadmin.blackfx.com/blackadmin", wait_until="networkidle")
    page.fill('input[type="email"], input[name="email"]', "lpadmin@blacktrader.com")
    page.fill('input[type="password"], input[name="password"]', "Raj1234!")
    page.click('button[type="submit"]')
    page.wait_for_timeout(3000)
    
    print("[2] Navigating to MEMBERS...")
    # Click on the button/tab with "MEMBERS"
    page.locator('text=MEMBERS').first.click()
    page.wait_for_timeout(3000)
    
    print("[3] Searching for mamf1@mailinator.com...")
    search_box = page.locator('input[placeholder*="Search"], input[type="search"]')
    if search_box.count() > 0:
        search_box.first.fill("mamf1@mailinator.com")
        page.wait_for_timeout(2000)
        
    print("[4] Checking table rows...")
    rows = page.locator("tbody tr").all()
    for i, r in enumerate(rows):
        print(f"Row {i}: {r.inner_text().replace(chr(10), ' | ')}")
        
    # Let's inspect the balance button in the row or clicking the member name
    # Earlier we saw in row:
    # "0.00 paper" button with tooltip: "paper: 0.00 | real: 10,000.00 | Click to set paper; open the member to fund the others."
    # Let's see what happens if we click on "0.00 paper"
    bal_btn = page.locator('button:has-text("paper"), button:has-text("0.00")').first
    if bal_btn.count() > 0:
        print("Found balance button in row:", bal_btn.inner_text())
        # Let's check its click behavior
        # But user specifically said: "admin->members->click member ->and set balance"
        
    # Let's click on the member name/email link
    print("[5] Clicking on member link...")
    mem_link = page.locator('text=mamf1@mailinator.com').first
    mem_link.click()
    page.wait_for_timeout(3000)
    
    page.screenshot(path="reports/screenshots/blackadmin/08_after_clicking_member.png", full_page=True)
    
    # Inspect what drawer or panel opened on the right or modal
    print("[6] Elements in the DOM now:")
    # Check for modals, drawers, dialogs, inputs, buttons
    all_buttons = page.locator('button, [role="button"], input, a').all()
    for b in all_buttons:
        txt = b.inner_text().strip()
        ph = b.get_attribute("placeholder") or ""
        aria = b.get_attribute("aria-label") or ""
        cls = b.get_attribute("class") or ""
        name = b.get_attribute("name") or ""
        if txt or ph or aria or name:
            print(f"  Tag: [{b.evaluate('e => e.tagName')}] Text: [{txt[:30]}] Placeholder: [{ph}] Name: [{name}] Cls: [{cls[:30]}]")
            
    browser.close()
