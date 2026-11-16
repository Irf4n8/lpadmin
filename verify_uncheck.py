import asyncio
from playwright.async_api import async_playwright

async def verify_state():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1400, 'height': 900})
        page = await context.new_page()
        
        await page.goto("https://lpadmin.blackfx.com/login", wait_until="networkidle")
        await page.fill('input[type="email"]', "mamfollower1@mailinator.com")
        await page.fill('input[type="password"]', "Test@1234")
        await page.click('button[type="submit"]')
        await page.wait_for_timeout(3000)
        
        await page.goto("https://lpadmin.blackfx.com/dashboard", wait_until="networkidle")
        await page.wait_for_timeout(6000)
        
        chart_frame = next((f for f in page.frames if "chartv2" in f.url), None)
        
        gear_btn = await chart_frame.query_selector('button[aria-label="Broker settings"]')
        await gear_btn.click()
        await page.wait_for_timeout(2000)
        
        chk = await chart_frame.query_selector('[data-popup="broker-settings"] input[type="checkbox"]')
        is_checked = await chk.is_checked()
        lbl = await chart_frame.evaluate("el => el.parentElement.innerText", chk)
        print(f"Re-check state for {lbl}: {is_checked}")
        
        # Check active tabs
        active_tabs = await chart_frame.query_selector_all('[data-popup="broker-settings"] button:has-text("Hedging"), [data-popup="broker-settings"] button:has-text("Netting")')
        for t in active_tabs:
            txt = await t.inner_text()
            dot = await t.query_selector(".rounded-full, [class*='bg-']")
            has_dot = bool(dot)
            print(f"Tab: {txt.strip()} -> dot: {has_dot}")
            
        await browser.close()

asyncio.run(verify_state())

