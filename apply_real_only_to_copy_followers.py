#!/usr/bin/env python3
"""
Configure Copy Trading Followers (follower1..100):
1. OMS: Unfollow on paper and paper-net; ensure follow on real and real-net.
2. UI: Disable Paper (Hedging & Netting); Enable Real (Hedging & Netting) via Playwright.
"""

import os
import sys
import time
import json
import asyncio
import requests
import concurrent.futures
from pathlib import Path
from typing import List, Dict, Any
from playwright.async_api import async_playwright

BASE_DIR = Path(__file__).resolve().parent
PROOF_DIR = BASE_DIR / "reports" / "evidence" / "broker_proofs"
PROOF_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_BASE_URL = "https://lpadmin.blackfx.com"
MEMBER_PASSWORD = os.getenv("MEMBER_PASSWORD", "Test@1234")
COPY_MASTER_CLIENT_ID = "mem_aac4ca423a6925dca7"

BROKER_TARGETS = {
    "Paper (Hedging)": False,
    "Paper (Netting)": False,
    "Real (Hedging)": True,
    "Real (Netting)": True
}

def sync_copy_oms(emails: List[str]):
    print(f"Syncing Copy OMS linkages on {len(emails)} Copy followers...")
    success_count = 0
    
    def worker(email):
        try:
            s = requests.Session()
            lr = s.post(f"{DEFAULT_BASE_URL}/api/auth/login", json={"email": email, "password": MEMBER_PASSWORD}, timeout=10)
            if lr.status_code != 200:
                return email, False
            tr = s.post(f"{DEFAULT_BASE_URL}/api/auth/chart-token", timeout=10)
            token = tr.json().get("token")
            if not token:
                return email, False
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            
            # Unfollow paper & paper-net
            for inst in ["paper", "paper-net"]:
                fr = s.get(f"{DEFAULT_BASE_URL}/v1/oms/{inst}/copy/follows", headers=headers, timeout=8)
                if fr.status_code == 200:
                    for fol in fr.json().get("following", []):
                        if fol.get("status") == "active":
                            s.post(f"{DEFAULT_BASE_URL}/v1/oms/{inst}/copy/unfollow", json={
                                "master_client_id": COPY_MASTER_CLIENT_ID,
                                "follow_id": fol.get("follow_id")
                            }, headers=headers, timeout=8)
                            
            # Ensure followed on real & real-net
            for inst in ["real", "real-net"]:
                fr = s.get(f"{DEFAULT_BASE_URL}/v1/oms/{inst}/copy/follows", headers=headers, timeout=8)
                acts = [f for f in fr.json().get("following", []) if f.get("status") == "active"] if fr.status_code == 200 else []
                if not acts:
                    s.post(f"{DEFAULT_BASE_URL}/v1/oms/{inst}/copy/follow", json={
                        "master_client_id": COPY_MASTER_CLIENT_ID,
                        "method": "balance",
                        "multiplier": 1.0,
                        "reverse": False,
                        "copy_mode": "public"
                    }, headers=headers, timeout=8)

            return email, True
        except Exception:
            return email, False

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futs = [executor.submit(worker, em) for em in emails]
        for f in concurrent.futures.as_completed(futs):
            em, ok = f.result()
            if ok:
                success_count += 1
                
    print(f"Copy OMS synchronized on: {success_count}/{len(emails)} accounts")
    return success_count

async def configure_ui_copy_follower(email: str, password: str = MEMBER_PASSWORD, retries: int = 2) -> Dict:
    for attempt in range(1, retries + 1):
        res = {
            "email": email,
            "success": False,
            "states": {},
            "error": None,
            "proof": None,
            "duration": 0
        }
        t0 = time.time()
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(viewport={'width': 1366, 'height': 768})
                page = await context.new_page()
                
                await page.goto(f"{DEFAULT_BASE_URL}/login", wait_until="networkidle", timeout=30000)
                await page.fill('input[type="email"]', email)
                await page.fill('input[type="password"]', password)
                await page.click('button[type="submit"]')
                await page.wait_for_timeout(2500)
                
                await page.goto(f"{DEFAULT_BASE_URL}/dashboard", wait_until="networkidle", timeout=35000)
                await page.wait_for_timeout(4500)
                
                chart_frame = next((f for f in page.frames if "chartv2" in f.url), None)
                if not chart_frame:
                    await browser.close()
                    if attempt < retries:
                        await asyncio.sleep(2)
                        continue
                    res["error"] = "chartv2 iframe not found"
                    return res
                    
                gear_btn = await chart_frame.query_selector('button[aria-label="Broker settings"]')
                if not gear_btn:
                    await browser.close()
                    if attempt < retries:
                        await asyncio.sleep(2)
                        continue
                    res["error"] = "Gear button not found"
                    return res
                    
                await gear_btn.click()
                await page.wait_for_timeout(1000)
                
                for tab_name, desired_state in BROKER_TARGETS.items():
                    tab_btn = await chart_frame.query_selector(f'[data-popup="broker-settings"] button:has-text("{tab_name}")')
                    if not tab_btn:
                        continue
                    await tab_btn.click()
                    await page.wait_for_timeout(500)
                    
                    chk = await chart_frame.query_selector('[data-popup="broker-settings"] input[type="checkbox"]')
                    if not chk:
                        continue
                        
                    curr_state = await chk.is_checked()
                    if curr_state != desired_state:
                        await chk.click()
                        await page.wait_for_timeout(700)
                        final_state = await chk.is_checked()
                    else:
                        final_state = curr_state
                        
                    res["states"][tab_name] = final_state

                all_match = all(res["states"].get(t) == expected for t, expected in BROKER_TARGETS.items())
                res["success"] = all_match
                
                prefix = email.split('@')[0]
                proof_path = os.path.join(PROOF_DIR, f"proof_{prefix}_real_only.png")
                await page.screenshot(path=proof_path)
                res["proof"] = proof_path
                
                await browser.close()
                res["duration"] = round(time.time() - t0, 2)
                
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

async def run_copy_fleet_ui(emails: List[str], concurrency: int = 6):
    sem = asyncio.Semaphore(concurrency)
    completed = 0
    total = len(emails)
    
    async def worker(em):
        nonlocal completed
        async with sem:
            r = await configure_ui_copy_follower(em)
            completed += 1
            status_icon = "✅" if r["success"] else "❌"
            print(f"[{completed}/{total}] {status_icon} {em:<32} | States: {r['states']} | Time: {r['duration']}s")
            return r

    tasks = [worker(em) for em in emails]
    return await asyncio.gather(*tasks)

def main():
    copy_followers = [f"follower{i}@mailinator.com" for i in range(1, 101)]
    # 1. OMS
    sync_copy_oms(copy_followers)
    # 2. UI
    results = asyncio.run(run_copy_fleet_ui(copy_followers, concurrency=6))
    success = sum(1 for r in results if r["success"])
    print(f"\nCopy Fleet UI: {success}/{len(copy_followers)} successfully updated to Real Only")
    
    report_file = BASE_DIR / "reports" / "evidence" / "broker_copy_followers_real_only_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    main()

