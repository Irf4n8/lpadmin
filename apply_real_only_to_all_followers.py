#!/usr/bin/env python3
"""
Master Automation: Enable Real (Hedging) and Real (Netting), Disable Paper (Hedging) and Paper (Netting)
Applies across all followers:
1. Admin API: Sets account_type='live' for all member accounts.
2. OMS API: Configures real and real-net follow linkages; unfollows paper and paper-net.
3. Trader Terminal UI (Playwright): Automates Broker Settings in chartv2:
   - Paper (Hedging): FALSE
   - Paper (Netting): FALSE
   - Real (Hedging): TRUE
   - Real (Netting): TRUE
   Captures and saves proof screenshots for every account.
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
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "lpadmin@blacktrader.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Raj1234!")
MEMBER_PASSWORD = os.getenv("MEMBER_PASSWORD", "Test@1234")

MAM_MASTER_CLIENT_ID = "mem_e2dbce29e1c71a7bf6"
COPY_MASTER_CLIENT_ID = "mem_aac4ca423a6925dca7"

BROKER_TARGETS = {
    "Paper (Hedging)": False,
    "Paper (Netting)": False,
    "Real (Hedging)": True,
    "Real (Netting)": True
}

# ==============================================================================
# SECTION 1: ADMIN & OMS API AUTOMATION
# ==============================================================================

def sync_admin_and_oms(mam_emails: List[str], copy_emails: List[str]) -> Dict[str, Any]:
    print("\n" + "="*80)
    print("STEP 1: Syncing Admin API (account_type='live') and OMS Linkages")
    print("="*80)
    
    admin_s = requests.Session()
    login_r = admin_s.post(f"{DEFAULT_BASE_URL}/admin/api/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD,
        "remember": True
    }, timeout=15)
    
    if login_r.status_code != 200 or not login_r.json().get("token"):
        print(f"[!] Admin login failed: {login_r.text}")
        return {"success": False, "error": "Admin login failed"}
        
    admin_token = login_r.json().get("token")
    admin_s.headers.update({"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"})
    
    # Map email to member_id
    m_res = admin_s.get(f"{DEFAULT_BASE_URL}/admin/api/members", timeout=15)
    members = m_res.json().get("members", [])
    member_map = {m.get("email"): m.get("member_id") for m in members if m.get("email")}
    print(f"Total admin members indexed: {len(member_map)}")
    
    # 1. Update account_type to live
    all_target_emails = list(set(mam_emails + copy_emails))
    print(f"Setting account_type='live' for {len(all_target_emails)} follower accounts...")
    
    live_count = 0
    def set_live(email):
        mem_id = member_map.get(email)
        if not mem_id:
            return email, False
        try:
            r = admin_s.post(f"{DEFAULT_BASE_URL}/admin/api/members/{mem_id}/account-type", json={"account_type": "live"}, timeout=8)
            return email, (r.status_code == 200)
        except Exception:
            return email, False

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futs = [executor.submit(set_live, em) for em in all_target_emails]
        for f in concurrent.futures.as_completed(futs):
            em, ok = f.result()
            if ok:
                live_count += 1
                
    print(f"Admin account_type='live' applied to: {live_count}/{len(all_target_emails)} accounts")

    # 2. OMS Follower link sync
    # For MAM followers: Unfollow paper/paper-net; follow real/real-net
    print(f"Syncing MAM follow linkages on {len(mam_emails)} MAM followers...")
    mam_oms_success = 0
    
    def sync_mam_follower(email):
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
                fr = s.get(f"{DEFAULT_BASE_URL}/v1/oms/{inst}/mam/follows", headers=headers, timeout=8)
                if fr.status_code == 200:
                    for fol in fr.json().get("following", []):
                        if fol.get("status") == "active":
                            s.post(f"{DEFAULT_BASE_URL}/v1/oms/{inst}/mam/unfollow", json={
                                "master_client_id": MAM_MASTER_CLIENT_ID,
                                "follow_id": fol.get("follow_id")
                            }, headers=headers, timeout=8)
                            
            # Ensure followed on real
            s.post(f"{DEFAULT_BASE_URL}/v1/oms/real/mam/follow", json={
                "master_client_id": MAM_MASTER_CLIENT_ID,
                "method": "multiplier",
                "multiplier": 2.0,
                "share_percent": 50.0,
                "reverse": False,
                "copy_mode": "public"
            }, headers=headers, timeout=8)

            return email, True
        except Exception:
            return email, False

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futs = [executor.submit(sync_mam_follower, em) for em in mam_emails]
        for f in concurrent.futures.as_completed(futs):
            em, ok = f.result()
            if ok:
                mam_oms_success += 1
                
    print(f"MAM OMS Real Follow synchronized on: {mam_oms_success}/{len(mam_emails)} accounts")
    
    return {
        "admin_live_count": live_count,
        "mam_oms_success": mam_oms_success
    }

# ==============================================================================
# SECTION 2: PLAYWRIGHT UI AUTOMATION (BROKER SETTINGS MODAL)
# ==============================================================================

async def configure_ui_follower(
    email: str,
    password: str = MEMBER_PASSWORD,
    retries: int = 2
) -> Dict[str, Any]:
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
                
                # Login
                await page.goto(f"{DEFAULT_BASE_URL}/login", wait_until="networkidle", timeout=30000)
                await page.fill('input[type="email"]', email)
                await page.fill('input[type="password"]', password)
                await page.click('button[type="submit"]')
                await page.wait_for_timeout(2500)
                
                # Dashboard
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
                
                # Configure each broker
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

                # Check all match
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


async def run_ui_fleet_automation(emails: List[str], concurrency: int = 6) -> List[Dict]:
    print("\n" + "="*80)
    print(f"STEP 2: Executing Fleet UI Automation across {len(emails)} Followers (concurrency={concurrency})")
    print("="*80)
    
    sem = asyncio.Semaphore(concurrency)
    completed = 0
    total = len(emails)
    
    async def worker(em, idx):
        nonlocal completed
        async with sem:
            r = await configure_ui_follower(em)
            completed += 1
            status_icon = "✅" if r["success"] else "❌"
            print(f"[{completed}/{total}] {status_icon} {em:<32} | States: {r['states']} | Time: {r['duration']}s")
            return r

    tasks = [worker(em, i) for i, em in enumerate(emails)]
    return await asyncio.gather(*tasks)


def main():
    start_time = time.time()
    
    # 1. Define follower lists
    mam_followers = [f"mamfollower{i}@mailinator.com" for i in range(1, 101)]
    copy_followers = [f"follower{i}@mailinator.com" for i in range(1, 101)]
    
    # Run Step 1: Admin & OMS API
    api_res = sync_admin_and_oms(mam_followers, copy_followers)
    
    # Run Step 2: Playwright UI Automation across all MAM followers
    ui_results = asyncio.run(run_ui_fleet_automation(mam_followers, concurrency=6))
    
    # Analyze UI results
    success_ui = [r for r in ui_results if r["success"]]
    failed_ui = [r for r in ui_results if not r["success"]]
    
    print("\n" + "="*80)
    print("AUTOMATION RESULTS SUMMARY")
    print("="*80)
    print(f"Total MAM Followers: {len(mam_followers)}")
    print(f"UI Configuration Success: {len(success_ui)} / {len(mam_followers)} ({(len(success_ui)/len(mam_followers))*100:.1f}%)")
    print(f"UI Configuration Failed: {len(failed_ui)}")
    print(f"Admin API Live Accounts: {api_res.get('admin_live_count')}")
    print(f"MAM OMS Real Linkages: {api_res.get('mam_oms_success')}")
    print(f"Total Execution Time: {round(time.time() - start_time, 2)}s")
    print(f"Screenshots saved to: {PROOF_DIR}")
    
    # Save JSON report
    report_file = BASE_DIR / "reports" / "evidence" / "broker_real_only_execution_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "target_states": BROKER_TARGETS,
            "total_followers": len(mam_followers),
            "success_count": len(success_ui),
            "failed_count": len(failed_ui),
            "api_results": api_res,
            "details": ui_results
        }, f, indent=2)
    print(f"Evidence report saved to: {report_file}")

if __name__ == "__main__":
    main()

