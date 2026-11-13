import asyncio
import os
from typing import List, Tuple, Dict
from playwright.async_api import async_playwright

BROKER_TAB_NAMES = {
    "paper": "Paper (Hedging)",
    "real": "Real (Hedging)",
    "paper-net": "Paper (Netting)",
    "real-net": "Real (Netting)"
}

async def toggle_single_follower_broker(
    email: str,
    password: str = "Test@1234",
    broker_key: str = "paper",
    enable: bool = False,
    headless: bool = True,
    save_proof: bool = False
) -> Dict:
    tab_name = BROKER_TAB_NAMES.get(broker_key, broker_key)
    res = {
        "email": email,
        "broker": tab_name,
        "action": "ENABLE" if enable else "DISABLE",
        "success": False,
        "previous_state": None,
        "final_state": None,
        "error": None,
        "proof_screenshot": None
    }
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context(viewport={'width': 1366, 'height': 768})
            page = await context.new_page()
            
            # 1. Login
            await page.goto("https://lpadmin.blackfx.com/login", wait_until="networkidle", timeout=25000)
            await page.fill('input[type="email"]', email)
            await page.fill('input[type="password"]', password)
            await page.click('button[type="submit"]')
            await page.wait_for_timeout(2500)
            
            # 2. Go to dashboard
            await page.goto("https://lpadmin.blackfx.com/dashboard", wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(4500)
            
            chart_frame = next((f for f in page.frames if "chartv2" in f.url), None)
            if not chart_frame:
                res["error"] = "chartv2 iframe not found"
                await browser.close()
                return res
                
            # 3. Click 'Broker settings' button
            gear_btn = await chart_frame.query_selector('button[aria-label="Broker settings"]')
            if not gear_btn:
                res["error"] = "Broker settings gear button not found"
                await browser.close()
                return res
                
            await gear_btn.click()
            await page.wait_for_timeout(1200)
            
            # 4. Click target broker tab
            tab_btn = await chart_frame.query_selector(f'[data-popup="broker-settings"] button:has-text("{tab_name}")')
            if not tab_btn:
                res["error"] = f"Tab {tab_name} not found"
                await browser.close()
                return res
                
            await tab_btn.click()
            await page.wait_for_timeout(1000)
            
            # 5. Check current checkbox state
            chk = await chart_frame.query_selector('[data-popup="broker-settings"] input[type="checkbox"]')
            if not chk:
                res["error"] = "Broker checkbox not found in tab"
                await browser.close()
                return res
                
            prev_state = await chk.is_checked()
            res["previous_state"] = prev_state
            
            # 6. Toggle if needed
            if prev_state != enable:
                await chk.click()
                await page.wait_for_timeout(1500)
                final_state = await chk.is_checked()
            else:
                final_state = prev_state
                
            res["final_state"] = final_state
            res["success"] = (final_state == enable)
            
            if save_proof or res["success"]:
                shot_name = f"proof_{email.split('@')[0]}_{broker_key}_{'enabled' if enable else 'disabled'}.png"
                await page.screenshot(path=shot_name)
                res["proof_screenshot"] = shot_name
                
            await browser.close()
            return res
            
    except Exception as e:
        res["error"] = str(e)
        return res

def run_toggle_single_sync(email: str, password: str = "Test@1234", broker_key: str = "paper", enable: bool = False) -> Dict:
    return asyncio.run(toggle_single_follower_broker(email, password, broker_key, enable))

async def toggle_batch_followers_broker(
    emails: List[str],
    password: str = "Test@1234",
    broker_key: str = "paper",
    enable: bool = False,
    concurrency: int = 3
) -> List[Dict]:
    sem = asyncio.Semaphore(concurrency)
    
    async def task(email):
        async with sem:
            return await toggle_single_follower_broker(
                email=email,
                password=password,
                broker_key=broker_key,
                enable=enable,
                headless=True,
                save_proof=False
            )
            
    tasks = [task(e) for e in emails]
    return await asyncio.gather(*tasks)

def run_toggle_batch_sync(emails: List[str], password: str = "Test@1234", broker_key: str = "paper", enable: bool = False, concurrency: int = 3) -> List[Dict]:
    return asyncio.run(toggle_batch_followers_broker(emails, password, broker_key, enable, concurrency))

if __name__ == "__main__":
    print("Testing follower_ui_automator...")
    result = run_toggle_single_sync("mamfollower1@mailinator.com", "Test@1234", "paper", enable=False)
    print("Toggle paper -> False:", result)
    result2 = run_toggle_single_sync("mamfollower1@mailinator.com", "Test@1234", "paper", enable=True)
    print("Toggle paper -> True:", result2)
