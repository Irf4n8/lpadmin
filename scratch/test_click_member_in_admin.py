from playwright.sync_api import sync_playwright
import time
import os

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    page.goto("https://lpadmin.blackfx.com/blackadmin", wait_until="networkidle")
    page.fill('input[type="email"], input[name="email"]', "lpadmin@blacktrader.com")
    page.fill('input[type="password"], input[name="password"]', "Raj1234!")
    page.click('button[type="submit"]')
    page.wait_for_timeout(3000)
    
    # 1. Admin -> Members
    print("Navigating to MEMBERS...")
    page.locator('text=MEMBERS').first.click()
    page.wait_for_timeout(3000)
    
    # Filter by exact email
    search_input = page.locator('input[placeholder*="email, name or user id"]').first
    search_input.fill("mamf1@mailinator.com")
    page.wait_for_timeout(1500)
    
    # Find the row with exact 'mamf1@mailinator.com'
    # In table, locate row containing text 'mamf1@mailinator.com'
    row = page.locator('tbody tr:has-text("mamf1@mailinator.com")').first
    print("Found row text:", row.inner_text().replace('\n', ' | '))
    
    # 2. Click member
    print("Clicking member name / link...")
    # Let's find clickable element inside row
    link = row.locator('text=mamf1@mailinator.com').first
    link.click()
    page.wait_for_timeout(3000)
    
    page.screenshot(path="reports/screenshots/blackadmin/09_member_drawer_open.png")
    print("Saved 09_member_drawer_open.png")
    
    # Check all text and inputs on screen now
    # Check if a drawer, aside, dialog, or modal is visible
    containers = page.locator('aside, dialog, [role="dialog"], .drawer, .modal, [class*="drawer"], [class*="modal"], [class*="sheet"]').all()
    print("Found containers:", len(containers))
    for i, c in enumerate(containers):
        print(f"Container {i} text preview:", c.inner_text()[:200].replace('\n', ' '))
        
    # Check all buttons and inputs in the drawer / modal
    drawer_inputs = page.locator('aside input, dialog input, [role="dialog"] input, [class*="drawer"] input').all()
    print("Drawer inputs:", len(drawer_inputs))
    for inp in drawer_inputs:
        print("  Drawer Input:", inp.get_attribute("placeholder"), inp.get_attribute("name"), inp.get_attribute("type"), inp.get_attribute("value"))
        
    drawer_buttons = page.locator('aside button, dialog button, [role="dialog"] button, [class*="drawer"] button').all()
    print("Drawer buttons:", len(drawer_buttons))
    for b in drawer_buttons:
        print("  Drawer Button:", b.inner_text().strip())
        
    # If no aside/dialog found, list all inputs and buttons on page
    if not drawer_inputs:
        print("Listing all inputs on page:")
        for inp in page.locator("input").all():
            print("  Input:", inp.get_attribute("placeholder"), inp.get_attribute("name"), inp.get_attribute("type"), inp.get_attribute("value"))
    if not drawer_buttons:
        print("Listing all buttons on page:")
        for b in page.locator("button").all():
            print("  Button:", b.inner_text().strip())

    browser.close()
