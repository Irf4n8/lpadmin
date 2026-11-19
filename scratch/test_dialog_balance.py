from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    
    dialogs = []
    def handle_dialog(dialog):
        print(f"!!! DIALOG DETECTED !!! Type: {dialog.type}, Message: {dialog.message}, Default: {dialog.default_value}")
        dialogs.append(dialog)
        dialog.accept("25000") # accept with test value
        
    page.on("dialog", handle_dialog)
    
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
    bal_btn = row.locator('button:has-text("paper")').first
    print("Clicking bal_btn...")
    bal_btn.click()
    page.wait_for_timeout(2000)
    
    print(f"Total dialogs captured: {len(dialogs)}")
    
    # Also check what the code on bal_btn does by looking at the page JS or onClick handler
    onclick_info = page.evaluate("""() => {
        const btn = document.querySelector('button[title*="Click to set paper"]');
        if (!btn) return 'btn not found';
        // Check react props or event listeners
        const key = Object.keys(btn).find(k => k.startsWith('__reactFiber') || k.startsWith('__reactProps'));
        return {
            hasReactProps: !!key,
            props: key ? Object.keys(btn[key]) : []
        };
    }""")
    print("React props on button:", onclick_info)
    
    browser.close()
