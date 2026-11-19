from playwright.sync_api import sync_playwright
import time

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
    page.locator('input[placeholder*="email, name or user id"]').first.fill("mamf1@mailinator.com")
    page.wait_for_timeout(1500)
    
    row = page.locator('tbody tr:has-text("mamf1@mailinator.com")').first
    print("=== ROW HTML ===")
    print(row.inner_html())
    
    # Also find all buttons in that row
    btns = row.locator("button, a").all()
    print(f"Buttons in row: {len(btns)}")
    for i, b in enumerate(btns):
        print(f"Btn {i}: text='{b.inner_text().strip()}', title='{b.get_attribute('title')}', aria='{b.get_attribute('aria-label')}'")

    browser.close()
