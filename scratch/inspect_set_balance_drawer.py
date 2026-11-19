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
    
    row_td0 = page.locator('tbody tr td').first
    row_td0.click()
    page.wait_for_timeout(2000)
    
    # Inspect the drawer structure and the elements around "Set balance"
    set_bal_btns = page.locator('button:has-text("Set balance")').all()
    print("Found Set balance buttons:", len(set_bal_btns))
    for i, btn in enumerate(set_bal_btns):
        parent_html = btn.evaluate("e => e.parentElement.parentElement.outerHTML")
        print(f"\n--- Set balance button {i} container ---")
        print(parent_html[:500])
        
    page.screenshot(path="reports/screenshots/blackadmin/13_member_drawer_balance_section.png")
    browser.close()
