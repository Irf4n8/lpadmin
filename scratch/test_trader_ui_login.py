from playwright.sync_api import sync_playwright
import time
import os

os.makedirs("reports/screenshots/blacktrader_ui", exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    
    print("Navigating to https://lpadmin.blackfx.com/login...")
    page.goto("https://lpadmin.blackfx.com/login", wait_until="networkidle")
    page.screenshot(path="reports/screenshots/blacktrader_ui/01_trader_login_page.png")
    
    # Fill login credentials for mamm
    print("Logging in as mamm@mailinator.com...")
    page.fill('input[type="email"], input[name="email"]', "mamm@mailinator.com")
    page.fill('input[type="password"], input[name="password"]', "12345678")
    page.click('button[type="submit"]')
    page.wait_for_timeout(4000)
    
    print("Current URL:", page.url)
    page.screenshot(path="reports/screenshots/blacktrader_ui/02_trader_after_login.png", full_page=True)
    
    # Check if iframe exists or direct trader terminal
    frames = page.frames
    print("Total frames:", len(frames))
    for i, f in enumerate(frames):
        print(f"Frame {i}: name='{f.name}', url='{f.url}'")
        
    # Inspect elements on page
    buttons = page.locator("button, a, [role='tab'], [role='button']").all()
    print("Interactive elements:", len(buttons))
    for b in buttons[:20]:
        t = b.inner_text().strip().replace('\n', ' ')
        if t:
            print(f"  [{b.evaluate('e => e.tagName')}]: '{t}'")
            
    browser.close()
