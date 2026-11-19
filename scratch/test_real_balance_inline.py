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
    
    # Target specifically the Real money "Set balance" button
    # In the Money card:
    # row 1 has "Trading balance · Real (Hedging)" and "Set balance"
    real_row = page.locator('.section-gap:has-text("Real (Hedging)")').first
    print("Real row text:", real_row.inner_text().replace('\n', ' | '))
    
    btn_real = real_row.locator('button:has-text("Set balance")').first
    print("Clicking Real Set balance button...")
    btn_real.click()
    page.wait_for_timeout(2000)
    
    page.screenshot(path="reports/screenshots/blackadmin/15_real_balance_inline_edit.png")
    
    # Check what is now inside real_row
    print("Real row after click:", real_row.inner_html())
    
    # Check all inputs inside real_row
    inputs = real_row.locator('input').all()
    print("Inputs found:", len(inputs))
    for inp in inputs:
        print("  Input:", inp.get_attribute("type"), inp.get_attribute("value"), inp.get_attribute("placeholder"))
        
    btns = real_row.locator('button').all()
    print("Buttons found:", len(btns))
    for b in btns:
        print("  Button:", b.inner_text().strip())

    browser.close()
