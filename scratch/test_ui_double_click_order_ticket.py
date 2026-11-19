from playwright.sync_api import sync_playwright
import time
import os

SCREENSHOT_DIR = os.path.abspath("reports/screenshots/race_ui")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

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
            
    # Open order ticket
    b_btn = chart_frame.locator('button[title*="Buy at ask"], button.a.b').first
    b_btn.click(force=True)
    page.wait_for_timeout(2000)
    
    # Locate the big submission button: `BUY 0.01 @ ...`
    submit_btn = chart_frame.locator('button:has-text("BUY 0.01"), button:has-text("BUY")').last
    print("Found submit button:", submit_btn.inner_text().strip())
    
    # Save screenshot of order ticket
    p_ticket = os.path.join(SCREENSHOT_DIR, "ui_net01_order_ticket_ready.png")
    page.screenshot(path=p_ticket)
    print("Saved:", p_ticket)
    
    # Now simulate rapid double-click on the submit button
    print("Executing rapid double click on submit button...")
    submit_btn.click()
    submit_btn.click()
    
    page.wait_for_timeout(4000)
    
    p_after = os.path.join(SCREENSHOT_DIR, "ui_net01_after_double_click.png")
    page.screenshot(path=p_after)
    print("Saved:", p_after)
    
    browser.close()
