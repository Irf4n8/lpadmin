import asyncio
from playwright.async_api import async_playwright

async def disable_paper_hedging():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1400, 'height': 900})
        page = await context.new_page()
        
        print("1. Logging in as mamfollower1@mailinator.com...")
        await page.goto("https://lpadmin.blackfx.com/login", wait_until="networkidle")
        await page.fill('input[type="email"]', "mamfollower1@mailinator.com")
        await page.fill('input[type="password"]', "Test@1234")
        await page.click('button[type="submit"]')
        await page.wait_for_timeout(3000)
        
        print("2. Going to dashboard...")
        await page.goto("https://lpadmin.blackfx.com/dashboard", wait_until="networkidle")
        await page.wait_for_timeout(6000)
        
        chart_frame = next((f for f in page.frames if "chartv2" in f.url), None)
        if not chart_frame:
            print("Chart frame not found!")
            await browser.close()
            return
            
        print("3. Clicking 'Broker settings' button...")
        gear_btn = await chart_frame.query_selector('button[aria-label="Broker settings"]')
        await gear_btn.click()
        await page.wait_for_timeout(2000)
        
        # In Paper (Hedging) tab (which is open by default):
        chk = await chart_frame.query_selector('[data-popup="broker-settings"] input[type="checkbox"]')
        is_checked = await chk.is_checked()
        print(f"Initial Checkbox state for Paper (Hedging): {is_checked}")
        
        if is_checked:
            print("4. Unchecking Enable Paper (Hedging)...")
            await chk.click()
            await page.wait_for_timeout(1000)
            
            new_checked = await chk.is_checked()
            print(f"New Checkbox state for Paper (Hedging): {new_checked}")
            
        # Click close button on modal
        close_btn = await chart_frame.query_selector('[data-popup="broker-settings"] button:has-text("Close")')
        if close_btn:
            await close_btn.click()
            await page.wait_for_timeout(1000)
            
        # Check Trades bar in terminal
        trades_text = await chart_frame.evaluate("() => document.querySelector('.xt-global')?.innerText || ''")
        print("Trades text summary after disable:")
        
        # Check active brokers in localStorage
        uid = await chart_frame.evaluate("() => window.__IFRAME_CONFIG__?.user_id")
        key = f"selectedBrokers:{uid}"
        ls_val = await chart_frame.evaluate("k => localStorage.getItem(k)", key)
        print(f"localStorage['{key}'] after disable:", ls_val)
        
        await page.screenshot(path="after_disable_paper.png")
        print("Screenshot saved to after_disable_paper.png")
        
        await browser.close()

asyncio.run(disable_paper_hedging())

