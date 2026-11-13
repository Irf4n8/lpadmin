import asyncio
from playwright.async_api import async_playwright

BROKER_TAB_NAMES = {
    "paper": "Paper (Hedging)",
    "real": "Real (Hedging)",
    "paper-net": "Paper (Netting)",
    "real-net": "Real (Netting)"
}

async def set_follower_broker_in_ui(email: str, password: str, broker_key: str, enable: bool):
    tab_name = BROKER_TAB_NAMES.get(broker_key, broker_key)
    print(f"\n[UI AUTOMATION] Target: {email} | Broker: {tab_name} | Action: {'ENABLE' if enable else 'DISABLE'}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1400, 'height': 900})
        page = await context.new_page()
        
        # 1. Login
        print("-> Logging in to lpadmin.blackfx.com...")
        await page.goto("https://lpadmin.blackfx.com/login", wait_until="networkidle")
        await page.fill('input[type="email"]', email)
        await page.fill('input[type="password"]', password)
        await page.click('button[type="submit"]')
        await page.wait_for_timeout(2500)
        
        # 2. Go to dashboard
        print("-> Navigating to /dashboard...")
        await page.goto("https://lpadmin.blackfx.com/dashboard", wait_until="networkidle")
        await page.wait_for_timeout(5000)
        
        chart_frame = next((f for f in page.frames if "chartv2" in f.url), None)
        if not chart_frame:
            print("ERROR: chartv2 iframe not found!")
            await browser.close()
            return False, "Chart frame not found"
            
        # 3. Click 'Broker settings' button
        print("-> Opening Broker settings popup...")
        gear_btn = await chart_frame.query_selector('button[aria-label="Broker settings"]')
        if not gear_btn:
            print("ERROR: Gear button not found!")
            await browser.close()
            return False, "Gear button not found"
            
        await gear_btn.click()
        await page.wait_for_timeout(1500)
        
        # 4. Click target broker tab
        print(f"-> Switching to tab: {tab_name}...")
        tab_btn = await chart_frame.query_selector(f'[data-popup="broker-settings"] button:has-text("{tab_name}")')
        if not tab_btn:
            print(f"ERROR: Tab {tab_name} not found!")
            await browser.close()
            return False, f"Tab {tab_name} not found"
            
        await tab_btn.click()
        await page.wait_for_timeout(1000)
        
        # 5. Check current checkbox state
        chk = await chart_frame.query_selector('[data-popup="broker-settings"] input[type="checkbox"]')
        if not chk:
            print("ERROR: Checkbox not found in tab!")
            await browser.close()
            return False, "Checkbox not found"
            
        current_state = await chk.is_checked()
        print(f"-> Current checkbox state for {tab_name}: {current_state}")
        
        # 6. Toggle if needed
        if current_state != enable:
            print(f"-> Clicking checkbox to set state to {enable}...")
            await chk.click()
            await page.wait_for_timeout(1500)
            final_state = await chk.is_checked()
            print(f"-> Verified final checkbox state: {final_state}")
        else:
            print(f"-> Checkbox is already {enable}, no toggle needed.")
            final_state = current_state
            
        # 7. Take screenshot for proof
        shot_path = f"proof_{email.split('@')[0]}_{broker_key}_{'enabled' if enable else 'disabled'}.png"
        await page.screenshot(path=shot_path)
        print(f"-> Proof screenshot saved: {shot_path}")
        
        await browser.close()
        return True, f"Successfully set {tab_name} to {enable} (state: {final_state})"

async def main():
    # Test sample account: mamfollower1@mailinator.com
    # 1. Disable Paper (Hedging)
    ok1, msg1 = await set_follower_broker_in_ui("mamfollower1@mailinator.com", "Test@1234", "paper", enable=False)
    print("Result 1:", ok1, msg1)
    
    # 2. Enable Real (Hedging)
    ok2, msg2 = await set_follower_broker_in_ui("mamfollower1@mailinator.com", "Test@1234", "real", enable=True)
    print("Result 2:", ok2, msg2)

asyncio.run(main())
