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
    
    page.locator('text=MEMBERS').first.click()
    page.wait_for_timeout(3000)
    
    inputs = page.locator("input").all()
    for i, inp in enumerate(inputs):
        print(f"Input {i}: placeholder='{inp.get_attribute('placeholder')}', type='{inp.get_attribute('type')}', class='{inp.get_attribute('class')}'")
        
    # Find the filter or search input
    search_input = page.locator('input[placeholder*="Filter by name"], input[placeholder*="Search"], input[placeholder*="email"]').first
    if search_input.count() > 0:
        print("Found search input! Filling 'mamf1'...")
        search_input.fill("mamf1")
        search_input.press("Enter")
        page.wait_for_timeout(2000)
        
    # Check rows now
    rows = page.locator("tbody tr").all()
    print(f"Total rows after search: {len(rows)}")
    for r in rows:
        print("Row:", r.inner_text().replace("\n", " | "))
        
    page.screenshot(path="reports/screenshots/blackadmin/search_result_mamf1.png")
    browser.close()
