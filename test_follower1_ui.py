import asyncio
from playwright.async_api import async_playwright

async def run():
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
            
        print("3. Chart frame found:", chart_frame.url[:80])
        await page.screenshot(path="page_dashboard.png")
        print("Screenshot saved to page_dashboard.png")
        
        # Check localStorage inside chart_frame
        uid = await chart_frame.evaluate("() => window.__IFRAME_CONFIG__?.user_id")
        print("User ID in chart frame:", uid)
        
        keys = await chart_frame.evaluate("() => Object.keys(localStorage)")
        print("localStorage keys in chart frame:", keys)
        for k in keys:
            if "broker" in k.lower():
                val = await chart_frame.evaluate("k => localStorage.getItem(k)", k)
                print(f"Key {k} = {val}")
                
        # Find the gear icon or broker settings button in the Trades module
        buttons = await chart_frame.query_selector_all("button")
        print(f"Total buttons in chart frame: {len(buttons)}")
        
        for btn in buttons:
            txt = (await btn.inner_text() or "").strip()
            aria = await btn.get_attribute("aria-label") or ""
            title = await btn.get_attribute("title") or ""
            html = await btn.inner_html()
            if "svg" in html and ("setting" in aria.lower() or "gear" in aria.lower() or not txt):
                print(f"Candidate icon button: aria='{aria}' title='{title}' txt='{txt}'")
                
        await browser.close()

asyncio.run(run())

