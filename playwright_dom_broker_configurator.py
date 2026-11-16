#!/usr/bin/env python3
"""
Playwright Pure-DOM Broker Settings Configurator
================================================
Performs 100% DOM-based UI interactions (NO API calls):
1. Logs into each follower account.
2. Navigates to /dashboard and locates the chart/trades frame.
3. Clicks the 'Broker settings' button in the Trades widget.
4. In the pop-up box with the four instances:
   - Paper (Hedging): Unticks the checkbox.
   - Paper (Netting): Unticks the checkbox.
   - Real (Hedging): Ticks the checkbox to enable.
   - Real (Netting): Ticks the checkbox to enable.
5. Clicks the Close button on the pop-up box to commit changes.
6. Captures proof screenshots for verification.
"""

import os
import sys
import time
import json
import asyncio
from pathlib import Path
from typing import List, Dict, Any
from playwright.async_api import async_playwright

BASE_DIR = Path(__file__).resolve().parent
PROOF_DIR = BASE_DIR / "reports" / "evidence" / "dom_broker_proofs"
PROOF_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://lpadmin.blackfx.com"
PASSWORD = "Test@1234"

async def configure_follower_via_dom(
    email: str,
    password: str = PASSWORD,
    retries: int = 2
) -> Dict[str, Any]:
    res = {
        "email": email,
        "success": False,
        "states": {},
        "error": None,
        "proof": None,
        "duration": 0
    }
    t0 = time.time()
    
    for attempt in range(1, retries + 1):
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(viewport={"width": 1400, "height": 900})
                page = await context.new_page()
                
                # 1. Login
                await page.goto(f"{BASE_URL}/login", wait_until="networkidle", timeout=30000)
                await page.fill('input[type="email"]', email)
                await page.fill('input[type="password"]', password)
                await page.click('button[type="submit"]')
                await page.wait_for_timeout(2500)
                
                # 2. Go to dashboard
                await page.goto(f"{BASE_URL}/dashboard", wait_until="networkidle", timeout=35000)
                await page.wait_for_timeout(5000)
                
                # 3. Locate trading chart frame
                chart_frame = next((f for f in page.frames if "chartv2" in f.url), None)
                if not chart_frame:
                    await browser.close()
                    if attempt < retries:
                        await asyncio.sleep(2)
                        continue
                    res["error"] = "chartv2 iframe not found"
                    return res
                    
                # 4. Click 'Broker settings' button
                gear_btn = await chart_frame.query_selector('button[aria-label="Broker settings"], button:has-text("Broker settings")')
                if not gear_btn:
                    await browser.close()
                    if attempt < retries:
                        await asyncio.sleep(2)
                        continue
                    res["error"] = "Broker settings button not found"
                    return res
                    
                await gear_btn.click()
                await page.wait_for_timeout(1200)
                
                # Verify modal opened
                modal = await chart_frame.query_selector('[data-popup="broker-settings"]')
                if not modal:
                    await browser.close()
                    if attempt < retries:
                        await asyncio.sleep(2)
                        continue
                    res["error"] = "Broker settings modal did not open"
                    return res

                # Target operations:
                # - Paper (Hedging) -> Untick
                # - Paper (Netting) -> Untick
                # - Real (Hedging) -> Tick
                # - Real (Netting) -> Tick
                actions = [
                    ("Paper (Hedging)", False),
                    ("Paper (Netting)", False),
                    ("Real (Hedging)", True),
                    ("Real (Netting)", True)
                ]
                
                for tab_name, desired_state in actions:
                    tab_btn = await chart_frame.query_selector(f'[data-popup="broker-settings"] button:has-text("{tab_name}")')
                    if not tab_btn:
                        continue
                    await tab_btn.click()
                    await page.wait_for_timeout(600)
                    
                    chk = await chart_frame.query_selector('[data-popup="broker-settings"] input[type="checkbox"]')
                    if not chk:
                        continue
                        
                    is_checked = await chk.is_checked()
                    if is_checked != desired_state:
                        # Click the checkbox in the DOM
                        await chk.click()
                        await page.wait_for_timeout(700)
                        final_state = await chk.is_checked()
                    else:
                        final_state = is_checked
                        
                    res["states"][tab_name] = final_state

                # 5. Click the Close button on the pop-up modal to commit
                close_btn = await chart_frame.query_selector('[data-popup="broker-settings"] button:has-text("Close"), [data-popup="broker-settings"] button[aria-label="Close"]')
                if close_btn:
                    await close_btn.click()
                    await page.wait_for_timeout(1200)

                # Check if all 4 states match requirements
                all_correct = (
                    res["states"].get("Paper (Hedging)") is False and
                    res["states"].get("Paper (Netting)") is False and
                    res["states"].get("Real (Hedging)") is True and
                    res["states"].get("Real (Netting)") is True
                )
                res["success"] = all_correct
                
                # 6. Capture proof screenshot
                prefix = email.split('@')[0]
                proof_path = str(PROOF_DIR / f"dom_{prefix}_real_enabled.png")
                await page.screenshot(path=proof_path)
                res["proof"] = proof_path
                res["duration"] = round(time.time() - t0, 2)
                
                await browser.close()
                if res["success"]:
                    return res
                elif attempt < retries:
                    await asyncio.sleep(2)
                    continue
                return res

        except Exception as e:
            res["error"] = str(e)
            res["duration"] = round(time.time() - t0, 2)
            if attempt < retries:
                await asyncio.sleep(2)
                continue
            return res
            
    return res


async def run_fleet_dom_automation(emails: List[str], concurrency: int = 5):
    print("=" * 80)
    print(f"STARTING PLAYWRIGHT PURE-DOM BROKER CONFIGURATION ({len(emails)} Accounts, concurrency={concurrency})")
    print("Rules: DOM clicks only | Real Hedging & Real Netting: TICKED | Paper: UNTICKED")
    print("=" * 80)
    
    sem = asyncio.Semaphore(concurrency)
    completed = 0
    total = len(emails)
    
    async def worker(em):
        nonlocal completed
        async with sem:
            r = await configure_follower_via_dom(em)
            completed += 1
            icon = "✅" if r["success"] else "❌"
            print(f"[{completed:3d}/{total:3d}] {icon} {em:<32} | Real(H)={r['states'].get('Real (Hedging)')} Real(N)={r['states'].get('Real (Netting)')} Paper(H)={r['states'].get('Paper (Hedging)')} Paper(N)={r['states'].get('Paper (Netting)')} | {r['duration']}s")
            return r

    tasks = [worker(em) for em in emails]
    return await asyncio.gather(*tasks)


def main():
    start_time = time.time()
    
    # Target all 100 MAM followers
    mam_followers = [f"mamfollower{i}@mailinator.com" for i in range(1, 101)]
    
    results = asyncio.run(run_fleet_dom_automation(mam_followers, concurrency=5))
    
    success_count = sum(1 for r in results if r["success"])
    fail_count = sum(1 for r in results if not r["success"])
    total_time = round(time.time() - start_time, 2)
    
    print("\n" + "=" * 80)
    print("PLAYWRIGHT DOM CONFIGURATION COMPLETE")
    print("=" * 80)
    print(f"Total Accounts Processed : {len(mam_followers)}")
    print(f"Successful (All Verified) : {success_count} / {len(mam_followers)} ({(success_count/len(mam_followers))*100:.1f}%)")
    print(f"Failed                    : {fail_count}")
    print(f"Total Duration            : {total_time}s")
    print(f"Proof Screenshots Folder  : {PROOF_DIR}")
    
    report_file = BASE_DIR / "reports" / "evidence" / "playwright_dom_broker_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "method": "Pure Playwright DOM manipulation (no API calls)",
            "total_followers": len(mam_followers),
            "success_count": success_count,
            "failed_count": fail_count,
            "total_duration_seconds": total_time,
            "details": results
        }, f, indent=2)
    print(f"JSON Report Saved         : {report_file}")

if __name__ == "__main__":
    main()

