from playwright.sync_api import sync_playwright
import time
import os

SCREENSHOT_DIR = os.path.abspath("reports/screenshots/blackadmin")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    
    page.goto("https://lpadmin.blackfx.com/blackadmin", wait_until="networkidle")
    page.fill('input[type="email"]', "lpadmin@blacktrader.com")
    page.fill('input[type="password"]', "Raj1234!")
    page.click('button[type="submit"]')
    time.sleep(3)
    
    page.locator('text=Members').first.click()
    time.sleep(2)
    inp = page.locator('input[placeholder*="email, name or user id"]').first
    inp.fill("mamf1@mailinator.com")
    time.sleep(3)
    
    row1 = page.locator('table tbody tr').first
    
    # 1. Click on member name span
    print("\n[1] Clicking on mamf1 name span...")
    name_span = row1.locator('span[title="mamf1@mailinator.com"]').first
    name_span.click()
    time.sleep(3)
    page.screenshot(path=os.path.join(SCREENSHOT_DIR, "07_clicked_member_name.png"))
    print("Saved 07_clicked_member_name.png")
    
    # Check dialogs/drawers
    dialog = page.locator('[role="dialog"], aside, .modal, .sheet, [class*="drawer"]')
    print("Dialogs/Drawers count:", dialog.count())
    if dialog.count() > 0:
        print("Dialog text snippet:\n", dialog.first.inner_text()[:600])
        # Find inputs inside dialog
        d_inputs = dialog.first.locator('input, button, select').all()
        print("Dialog inputs/buttons:")
        for di in d_inputs:
            t = di.inner_text().strip().replace('\n', ' ')
            val = di.get_attribute('value') or ''
            p_holder = di.get_attribute('placeholder') or ''
            print(f"  [{t}] val:[{val}] placeholder:[{p_holder}]")

    # 2. Click on balance button
    print("\n[2] Clicking on Balance button in row...")
    bal_btn = row1.locator('button[title*="Click to set paper"]').first
    if bal_btn.count() > 0:
        bal_btn.click()
        time.sleep(3)
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "08_clicked_balance_button.png"))
        print("Saved 08_clicked_balance_button.png")
        dialog2 = page.locator('[role="dialog"], .modal, .popover')
        if dialog2.count() > 0:
            print("Balance popover/dialog text:\n", dialog2.first.inner_text()[:600])

    browser.close()

print("\nFinished testing member and balance buttons.")
