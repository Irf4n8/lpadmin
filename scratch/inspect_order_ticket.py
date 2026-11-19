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
    
    # Click on the 'B' button in the watchlist row
    # In earlier dump: `Btn: 'B' cls='a b svelte-1jzfxp'`
    b_btn = chart_frame.locator('button.a.b').first
    print("Clicking 'B' button...")
    b_btn.click()
    page.wait_for_timeout(2000)
    
    # Check what opened
    page.screenshot(path="reports/screenshots/race_ui/order_ticket_opened.png")
    
    # Find all visible buttons and inputs in chart frame
    visible_inputs = chart_frame.locator('input:visible').all()
    print("Visible inputs count:", len(visible_inputs))
    for inp in visible_inputs:
        print(f"  Inp: id='{inp.get_attribute('id')}' type='{inp.get_attribute('type')}' val='{inp.get_attribute('value')}' placeholder='{inp.get_attribute('placeholder')}'")
        
    visible_btns = chart_frame.locator('button:visible').all()
    print("Visible buttons count:", len(visible_btns))
    for b in visible_btns[-15:]:
        print(f"  Btn: '{b.inner_text().strip().replace(chr(10), ' ')}' cls='{b.get_attribute('class')}'")

    browser.close()
