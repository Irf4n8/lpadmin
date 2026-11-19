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
    
    # Save screenshot of loaded dashboard
    page.screenshot(path="reports/screenshots/blacktrader_ui/04_terminal_loaded.png")
    
    # Target frame 1
    chart_frame = None
    for f in page.frames:
        if "chartv2.blacktrader.com" in f.url:
            chart_frame = f
            break
            
    if chart_frame:
        print("Found chart frame:", chart_frame.url[:80])
        chart_frame.wait_for_load_state("domcontentloaded")
        time.sleep(3)
        
        # Check text and buttons inside chart frame
        buttons = chart_frame.locator("button, [role='button'], .btn, [class*='button']").all()
        print(f"Buttons inside chart frame: {len(buttons)}")
        for b in buttons[:30]:
            t = b.inner_text().strip().replace('\n', ' ')
            cls = b.get_attribute("class") or ""
            if t or cls:
                print(f"  Btn: '{t[:30]}' cls='{cls[:30]}'")
                
        # Check inputs inside chart frame
        inputs = chart_frame.locator("input").all()
        print(f"Inputs inside chart frame: {len(inputs)}")
        for inp in inputs:
            print(f"  Inp: type='{inp.get_attribute('type')}' val='{inp.get_attribute('value')}' placeholder='{inp.get_attribute('placeholder')}' cls='{inp.get_attribute('class')}'")
            
        # Check tabs like Positions, Orders, History
        tabs = chart_frame.locator("[role='tab'], .tab, [class*='tab']").all()
        print(f"Tabs inside chart frame: {len(tabs)}")
        for tb in tabs:
            print(f"  Tab: '{tb.inner_text().strip()}'")
    else:
        print("Chart frame not found!")

    browser.close()
