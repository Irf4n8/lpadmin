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
    
    print("Account page URL:", page.url)
    
    # Check what Open terminal links to
    term_link = page.locator('a:has-text("Open terminal")').first
    href = term_link.get_attribute("href")
    target = term_link.get_attribute("target")
    print(f"Open terminal href: {href}, target: {target}")
    
    # Let's click it or navigate to it
    term_link.click()
    page.wait_for_timeout(5000)
    
    print("After click, total pages:", len(page.context.pages))
    active_page = page.context.pages[-1]
    print("Active page URL:", active_page.url)
    active_page.screenshot(path="reports/screenshots/blacktrader_ui/03_trader_terminal.png", full_page=True)
    
    # Check elements on terminal page
    frames = active_page.frames
    print(f"Total frames on terminal: {len(frames)}")
    for i, f in enumerate(frames):
        print(f"Frame {i}: name='{f.name}', url='{f.url}'")
        
    browser.close()
