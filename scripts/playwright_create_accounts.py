#!/usr/bin/env python3
"""
Playwright BlackTrader Member Account Creation & Balance Funding
================================================================
Automates creating member accounts and funding balances using Playwright browser automation.
Settings and credentials are read from config.settings (.env).

Usage:
    python scripts/playwright_create_accounts.py --start 1 --end 100
    python scripts/playwright_create_accounts.py --headed --start 1 --end 10
"""

import argparse
import sys
import time
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config.settings import (
    BASE_URL,
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    MEMBER_PASSWORD,
    DEFAULT_BALANCE,
    DEFAULT_PREFIX,
    DEFAULT_DOMAIN,
    DEFAULT_INSTANCES,
)
from playwright.sync_api import sync_playwright


def create_accounts(args):
    if not args.admin_email or not args.admin_pass:
        print("[-] Error: Admin credentials missing. Configure ADMIN_EMAIL and ADMIN_PASSWORD in .env or pass via CLI.")
        sys.exit(1)

    if not args.member_pass:
        print("[-] Error: Member password missing. Configure MEMBER_PASSWORD in .env or pass via CLI.")
        sys.exit(1)

    headless = not args.headed

    print("\n" + "=" * 70)
    print(" BlackTrader Playwright Account Creator & Funder")
    print("=" * 70)
    print(f"[*] Base URL       : {args.url}")
    print(f"[*] Admin Email    : {args.admin_email}")
    print(f"[*] Target Range   : {args.prefix}{args.start}@{args.domain} -> {args.prefix}{args.end}@{args.domain}")
    print(f"[*] Target Balance : {args.balance:,.2f} ({args.instances})")
    print(f"[*] Headless Mode  : {headless}")
    print("=" * 70 + "\n")

    instances = [i.strip() for i in args.instances.split(",") if i.strip()]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, slow_mo=args.slow_mo)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        # Step 1: Admin login
        admin_url = f"{args.url.rstrip('/')}/blackadmin"
        print(f"[*] Navigating to {admin_url}...")
        page.goto(admin_url, wait_until="networkidle")

        print(f"[*] Logging in as admin ({args.admin_email})...")
        page.locator('input[type="email"], input[placeholder*="email" i]').fill(args.admin_email)
        page.locator('input[type="password"]').fill(args.admin_pass)

        with page.expect_response(lambda r: "/admin/api/login" in r.url and r.status == 200, timeout=15000):
            page.locator('button:has-text("Sign in")').click()

        page.wait_for_function("() => !!localStorage.getItem('oms_admin_token')", timeout=15000)
        token = page.evaluate("() => localStorage.getItem('oms_admin_token')")
        print(f"[+] Admin login successful! Token: {token[:8]}...")

        # Step 2: Navigate to Members section
        members_btn = page.locator('nav button:has-text("Members"), button:has-text("Members")').first
        if members_btn.is_visible():
            members_btn.click()
            page.wait_for_timeout(1000)

        existing_members = page.evaluate("""
            async () => {
                const token = localStorage.getItem('oms_admin_token');
                const resp = await fetch('/admin/api/members', {
                    headers: { 'Authorization': 'Bearer ' + token }
                });
                const data = await resp.json();
                return data.members || [];
            }
        """)
        existing_emails = {m.get("email"): m for m in existing_members if "email" in m}
        print(f"[+] Total existing members on platform: {len(existing_emails)}")

        total_to_process = args.end - args.start + 1
        created_count = 0
        funded_count = 0

        # Step 3: Process accounts
        for i in range(args.start, args.end + 1):
            email = f"{args.prefix}{i}@{args.domain}"
            member_id = None

            if email in existing_emails:
                member_id = existing_emails[email].get("member_id")
                print(f"[{i}/{args.end}] {email} already exists (ID: {member_id}). Updating balance...")
            else:
                result = page.evaluate("""
                    async ({ email, password }) => {
                        const token = localStorage.getItem('oms_admin_token');
                        const resp = await fetch('/admin/api/members', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'Authorization': 'Bearer ' + token
                            },
                            body: JSON.stringify({ email, password, name: '' })
                        });
                        const data = await resp.json();
                        return { ok: resp.ok, status: resp.status, data };
                    }
                """, {"email": email, "password": args.member_pass})

                if result.get("ok"):
                    member_data = result.get("data", {}).get("member", {})
                    member_id = member_data.get("member_id")
                    created_count += 1
                    print(f"[{i}/{args.end}] [CREATED] {email} -> ID: {member_id}")
                else:
                    print(f"[{i}/{args.end}] [-] Failed to create {email}: {result}")
                    continue

            # Fund accounts
            if member_id:
                for inst in instances:
                    page.evaluate("""
                        async ({ member_id, balance, instance }) => {
                            const token = localStorage.getItem('oms_admin_token');
                            const resp = await fetch(`/admin/api/members/${member_id}/balance`, {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/json',
                                    'Authorization': 'Bearer ' + token
                                },
                                body: JSON.stringify({
                                    instance: instance,
                                    balance: balance,
                                    remark: 'Playwright automation funding',
                                    force: true
                                })
                            });
                            return { ok: resp.ok, status: resp.status };
                        }
                    """, {"member_id": member_id, "balance": args.balance, "instance": inst})

                funded_count += 1
                print(f"         [FUNDED] {args.balance:,.2f} set on {instances}")

            time.sleep(0.05)

        page.reload(wait_until="networkidle")
        page.wait_for_timeout(1000)

        print("\n" + "=" * 70)
        print(f"[+] COMPLETED!")
        print(f"[+] New accounts created : {created_count}")
        print(f"[+] Accounts funded      : {funded_count}/{total_to_process}")
        print("=" * 70)

        browser.close()


def main():
    parser = argparse.ArgumentParser(description="Playwright BlackTrader Account Creator")
    parser.add_argument("--url", default=BASE_URL, help="Base admin URL (default: from config/settings.py)")
    parser.add_argument("--admin-email", default=ADMIN_EMAIL, help="Admin login email (default: from config/settings.py)")
    parser.add_argument("--admin-pass", default=ADMIN_PASSWORD, help="Admin login password (default: from config/settings.py)")
    parser.add_argument("--prefix", default=DEFAULT_PREFIX, help="Email prefix (default: from config/settings.py)")
    parser.add_argument("--domain", default=DEFAULT_DOMAIN, help="Email domain (default: from config/settings.py)")
    parser.add_argument("--member-pass", default=MEMBER_PASSWORD, help="Password for members (default: from config/settings.py)")
    parser.add_argument("--start", type=int, default=1, help="Starting index (default: 1)")
    parser.add_argument("--end", type=int, default=100, help="Ending index (default: 100)")
    parser.add_argument("--balance", type=float, default=DEFAULT_BALANCE, help="Balance amount (default: from config/settings.py)")
    parser.add_argument("--instances", default=DEFAULT_INSTANCES, help="Comma-separated instances: paper,real")
    parser.add_argument("--headed", action="store_true", help="Launch visible browser window")
    parser.add_argument("--slow-mo", type=int, default=0, help="Slow down Playwright actions by N ms")
    args = parser.parse_args()

    create_accounts(args)


if __name__ == "__main__":
    main()

