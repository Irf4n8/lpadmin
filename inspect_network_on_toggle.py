import asyncio
from playwright.async_api import async_playwright

async def inspect():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        requests_log = []
        
        page.on("request", lambda req: requests_log.append(f"[{req.method}] {req.url}"))
        
        print("Logging in...")
        await page.goto("https://lpadmin.blackfx.com/login", wait_until="networkidle")
        await page.fill('input[type="email"]', "mamfollower1@mailinator.com")
        await page.fill('input[type="password"]', "Test@1234")
        await page.click('button[type="submit"]')
        await page.wait_for_timeout(3000)
        
        print("Navigating to dashboard...")
        await page.goto("https://lpadmin.blackfx.com/dashboard", wait_until="networkidle")
        await page.wait_for_timeout(5000)
        
        chart_frame = next((f for f in page.frames if "chartv2" in f.url), None)
        if not chart_frame:
            print("No chart frame!")
            await browser.close()
            return
            
        gear_btn = await chart_frame.query_selector('button[aria-label="Broker settings"]')
        await gear_btn.click()
        await page.wait_for_timeout(1000)
        
        tab_btn = await chart_frame.query_selector('[data-popup="broker-settings"] button:has-text("Real (Hedging)")')
        await tab_btn.click()
        await page.wait_for_timeout(1000)
        
        chk = await chart_frame.query_selector('[data-popup="broker-settings"] input[type="checkbox"]')
        
        # Clear log before click
        requests_log.clear()
        print("--- CLICKING CHECKBOX NOW ---")
        await chk.click()
        await page.wait_for_timeout(3000)
        
        print(f"Total network requests captured during checkbox toggle: {len(requests_log)}")
        for r in requests_log:
            print("REQ:", r)
            
        await browser.close()

asyncio.run(inspect())

