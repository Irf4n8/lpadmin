from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    
    # Catch any dialogs
    def on_dialog(dialog):
        print(f"DIALOG PROMPT: {dialog.type} - {dialog.message}")
        dialog.accept("50000")
        
    page.on("dialog", on_dialog)
    
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
    
    # Dump entire Money card HTML
    money_card_html = page.evaluate("""() => {
        const h2s = Array.from(document.querySelectorAll('h2'));
        const moneyH2 = h2s.find(h => h.innerText.includes('Money'));
        return moneyH2 ? moneyH2.closest('.card').outerHTML : 'Money card not found';
    }""")
    print("=== MONEY CARD HTML ===")
    print(money_card_html)
    
    # Now let's click the Real balance "Set balance" button
    # Let's find all "Set balance" buttons
    buttons = page.locator('.card:has-text("Money") button:has-text("Set balance")').all()
    print(f"Found {len(buttons)} 'Set balance' buttons in Money card.")
    
    for i, btn in enumerate(buttons):
        print(f"Clicking button {i}...")
        btn.click()
        page.wait_for_timeout(1000)
        
    page.screenshot(path="reports/screenshots/blackadmin/14_set_balance_clicked.png")
    browser.close()
