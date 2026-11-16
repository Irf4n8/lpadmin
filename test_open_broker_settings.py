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
            
        print("3. Clicking 'Broker settings' button...")
        gear_btn = await chart_frame.query_selector('button[aria-label="Broker settings"]')
        if not gear_btn:
            print("Broker settings button not found!")
            await browser.close()
            return
            
        await gear_btn.click()
        await page.wait_for_timeout(2000)
        
        # Check if modal opened
        modal = await chart_frame.query_selector('[data-popup="broker-settings"]')
        print("Modal found:", bool(modal))
        if modal:
            # Check tabs
            tabs = await chart_frame.query_selector_all('[data-popup="broker-settings"] button, [data-popup="broker-settings"] [role="tab"]')
            print("Modal buttons/tabs count:", len(tabs))
            for t in tabs:
                txt = (await t.inner_text() or "").strip()
                print("Modal tab/button:", txt)
                
            # Check checkbox
            chk = await chart_frame.query_selector('[data-popup="broker-settings"] input[type="checkbox"]')
            if chk:
                is_checked = await chk.is_checked()
                lbl = await chart_frame.evaluate("el => el.parentElement.innerText", chk)
                print(f"Checkbox state: {is_checked}, Label: {lbl}")
                
        await page.screenshot(path="broker_settings_modal.png")
        print("Screenshot saved to broker_settings_modal.png")
        
        await browser.close()

asyncio.run(run())

