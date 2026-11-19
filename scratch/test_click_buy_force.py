from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    page.goto("https://lpadmin.blackfx.com/login", wait_until="networkidle")
    page.fill('input[type="email"], input[name="email"]', "mamm@mailinator.com")
    page.fill('input[type="password"], input[name="password"]', "12345678")
    page.click('button[type="submit"]')
    page.wait_for_timeout(3000)
    
    page.goto("https://lpadmin.blackfx.com/dashboard", wait_until="networkidle")
    page.wait_for_timeout(6000)
    
    chart_frame = None
    for f in page.frames:
        if "chartv2.blacktrader.com" in f.url:
            chart_frame = f
            break
            
    print("Found Chart Frame:", chart_frame.url[:60])
    
    # Click 'Buy at ask' with force=True
    b_btn = chart_frame.locator('button[title*="Buy at ask"], button.a.b').first
    print("Clicking 'Buy at ask' with force=True...")
    b_btn.click(force=True)
    page.wait_for_timeout(3000)
    
    page.screenshot(path="reports/screenshots/race_ui/after_buy_at_ask_click.png")
    print("Screenshot saved to reports/screenshots/race_ui/after_buy_at_ask_click.png")

    # Let's see what dialog, modal, or toast appeared
    toasts = chart_frame.locator('.toast, [role="alert"], .notification, .modal, dialog, [role="dialog"]').all()
    print("Toasts/Alerts found:", len(toasts))
    for t in toasts:
        print("  Alert:", t.inner_text().replace('\n', ' '))
        
    browser.close()
