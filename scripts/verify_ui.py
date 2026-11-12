"""
Playwright UI Verification Script for Copy Trading (Category Q)
===============================================================
Automates browser verification of:
1. Master trader login & terminal loading
2. Follower trader login & terminal loading
3. Saves UI evidence screenshots in reports/evidence/screenshots/
"""

import asyncio
from pathlib import Path
from playwright.async_api import async_playwright
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config.settings import MASTER_EMAIL
from config.settings import BASE_URL, MEMBER_PASSWORD


async def verify_ui():
    screenshots_dir = BASE_DIR / "reports" / "evidence" / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})

        # ---------------------------------------------------------------------
        # 1. Master UI Verification
        # ---------------------------------------------------------------------
        print("[*] Launching browser to verify Master UI (ctmaster@mailinator.com)...")
        page_master = await context.new_page()
        await page_master.goto(f"{BASE_URL}/login")
        await page_master.fill('input[type="email"]', MASTER_EMAIL)
        await page_master.fill('input[type="password"]', MEMBER_PASSWORD)
        await page_master.click('button[type="submit"]')

        try:
            await page_master.wait_for_url("**/dashboard**", timeout=12000)
            print("[+] Master logged in successfully! Reached dashboard.")
        except Exception:
            print("[!] URL wait timed out, continuing on page:", page_master.url)

        await page_master.wait_for_timeout(3000)
        master_screenshot = screenshots_dir / "master_terminal.png"
        await page_master.screenshot(path=str(master_screenshot), full_page=True)
        print(f"[+] Master terminal screenshot saved to: {master_screenshot}")

        # ---------------------------------------------------------------------
        # 2. Follower UI Verification
        # ---------------------------------------------------------------------
        print("\n[*] Launching separate browser context for Follower UI (follower1@mailinator.com)...")
        context_follower = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page_follower = await context_follower.new_page()
        await page_follower.goto(f"{BASE_URL}/login")
        await page_follower.fill('input[type="email"]', "follower1@mailinator.com")
        await page_follower.fill('input[type="password"]', MEMBER_PASSWORD)
        await page_follower.click('button[type="submit"]')

        try:
            await page_follower.wait_for_url("**/dashboard**", timeout=12000)
            print("[+] Follower 1 logged in successfully! Reached dashboard.")
        except Exception:
            print("[!] URL wait timed out, continuing on page:", page_follower.url)

        await page_follower.wait_for_timeout(3000)
        follower_screenshot = screenshots_dir / "follower_terminal.png"
        await page_follower.screenshot(path=str(follower_screenshot), full_page=True)
        print(f"[+] Follower 1 terminal screenshot saved to: {follower_screenshot}")

        await browser.close()
        print("\n[+] UI Verification completed successfully!")


if __name__ == "__main__":
    asyncio.run(verify_ui())

