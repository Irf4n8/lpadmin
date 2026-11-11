#!/usr/bin/env python3
"""
Playwright BlackTrader Copy Trading Follow Automation
=====================================================
Automates follower accounts following a master trader using Playwright.
Settings and credentials are read from config.settings (.env).

Usage:
    python scripts/playwright_follow_master.py --list-masters
    python scripts/playwright_follow_master.py --master "ctmaster" --start 1 --end 100
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
    MEMBER_PASSWORD,
    DEFAULT_PREFIX,
    DEFAULT_DOMAIN,
)
from playwright.sync_api import sync_playwright


def list_masters_playwright(args):
    """Launch Playwright browser, fetch and display all registered copy masters."""
    if not args.password:
        print("[-] Error: Follower password missing. Configure MEMBER_PASSWORD in .env or pass --password.")
        sys.exit(1)

    probe_email = f"{args.prefix}{args.start}@{args.domain}"
    headless = not args.headed

    print(f"[*] Launching Playwright browser (headless={headless})...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()

        print(f"[*] Logging in with probe follower ({probe_email})...")
        login_res = context.request.post(
            f"{args.url.rstrip('/')}/api/auth/login",
            data={"email": probe_email, "password": args.password}
        )
        if login_res.status != 200:
            print(f"[-] Login failed for probe account {probe_email}: HTTP {login_res.status} - {login_res.text()}")
            browser.close()
            sys.exit(1)

        # Get chart token
        chart_res = context.request.post(f"{args.url.rstrip('/')}/api/auth/chart-token")
        if chart_res.status != 200:
            print(f"[-] Could not retrieve chart token: HTTP {chart_res.status}")
            browser.close()
            sys.exit(1)

        chart_token = chart_res.json().get("token")
        if not chart_token:
            print("[-] No chart token returned in response.")
            browser.close()
            sys.exit(1)

        instance = "paper" if args.instance == "both" else args.instance
        masters_res = context.request.get(
            f"{args.url.rstrip('/')}/v1/oms/{instance}/copy/masters",
            headers={"Authorization": f"Bearer {chart_token}"}
        )
        if masters_res.status != 200:
            print(f"[-] Failed to fetch masters: HTTP {masters_res.status}")
            browser.close()
            sys.exit(1)

        masters = masters_res.json().get("masters", [])
        if not masters:
            print(f"[-] No masters found on instance '{instance}'.")
        else:
            print("\n" + "=" * 85)
            print(f"{'MASTER NAME':<22} | {'CLIENT ID':<26} | {'KIND':<16} | {'FOLLOWERS':<9} | {'GROWTH'}")
            print("-" * 85)
            for m in masters:
                name = m.get("name", "N/A")
                cid = m.get("client_id", "N/A")
                kind = m.get("kind", "N/A")
                stats = m.get("stats", {})
                followers = stats.get("followers", 0)
                growth = stats.get("growth", 0)
                print(f"{name:<22} | {cid:<26} | {kind:<16} | {followers:<9} | {growth}")
            print("=" * 85 + "\n")

        browser.close()


def follow_master_playwright(args):
    """Automate follower accounts to follow target master using Playwright."""
    if not args.password:
        print("[-] Error: Follower password missing. Configure MEMBER_PASSWORD in .env or pass --password.")
        sys.exit(1)

    headless = not args.headed
    probe_email = f"{args.prefix}{args.start}@{args.domain}"

    print("\n" + "=" * 75)
    print(" BlackTrader Playwright Copy Trading Follower")
    print("=" * 75)
    print(f"[*] Base URL       : {args.url}")
    print(f"[*] Target Master  : {args.master}")
    print(f"[*] Followers      : {args.prefix}{args.start}@{args.domain} -> {args.prefix}{args.end}@{args.domain}")
    print(f"[*] Instance       : {args.instance}")
    print(f"[*] Method         : {args.method} (Multiplier: {args.multiplier})")
    print(f"[*] Reverse Copy   : {args.reverse}")
    print(f"[*] Headless Mode  : {headless}")
    print("=" * 75 + "\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, slow_mo=args.slow_mo)
        probe_context = browser.new_context()

        # Step 1: Resolve master client ID
        print(f"[*] Resolving master client ID for '{args.master}'...")
        login_res = probe_context.request.post(
            f"{args.url.rstrip('/')}/api/auth/login",
            data={"email": probe_email, "password": args.password}
        )
        if login_res.status != 200:
            print(f"[-] Could not login with initial probe account {probe_email}.")
            browser.close()
            sys.exit(1)

        token_res = probe_context.request.post(f"{args.url.rstrip('/')}/api/auth/chart-token")
        chart_token = token_res.json().get("token")
        if not chart_token:
            print("[-] Could not retrieve chart token.")
            browser.close()
            sys.exit(1)

        lookup_instance = "paper" if args.instance == "both" else args.instance
        masters_res = probe_context.request.get(
            f"{args.url.rstrip('/')}/v1/oms/{lookup_instance}/copy/masters",
            headers={"Authorization": f"Bearer {chart_token}"}
        )
        masters_data = masters_res.json().get("masters", [])

        target_master_id = None
        if args.master.startswith("mem_"):
            target_master_id = args.master
        else:
            for m in masters_data:
                if m.get("name", "").strip().lower() == args.master.strip().lower():
                    target_master_id = m.get("client_id")
                    break

        if not target_master_id:
            print(f"[-] Could not find master '{args.master}'. Run with --list-masters to see valid names.")
            browser.close()
            sys.exit(1)

        print(f"[+] Master resolved: '{args.master}' -> ID: {target_master_id}\n")
        probe_context.close()

        target_instances = ["paper", "real"] if args.instance == "both" else [args.instance]
        total_followers = args.end - args.start + 1
        success_count = 0

        # Step 2: Iterate over all followers
        for i in range(args.start, args.end + 1):
            email = f"{args.prefix}{i}@{args.domain}"
            acc_context = browser.new_context()

            # Trader login
            login_result = acc_context.request.post(
                f"{args.url.rstrip('/')}/api/auth/login",
                data={"email": email, "password": args.password}
            )

            if login_result.status != 200:
                print(f"[{i}/{args.end}] [-] Login failed for {email}: HTTP {login_result.status}")
                acc_context.close()
                continue

            # Mint chart token
            token_res = acc_context.request.post(f"{args.url.rstrip('/')}/api/auth/chart-token")
            trader_token = token_res.json().get("token")
            if not trader_token:
                print(f"[{i}/{args.end}] [-] Failed to obtain chart token for {email}")
                acc_context.close()
                continue

            # Follow master
            account_success = True
            for inst in target_instances:
                payload = {
                    "master_client_id": target_master_id,
                    "method": args.method,
                    "multiplier": args.multiplier,
                    "reverse": args.reverse,
                    "copy_mode": args.copy_mode
                }
                follow_res = acc_context.request.post(
                    f"{args.url.rstrip('/')}/v1/oms/{inst}/copy/follow",
                    headers={"Authorization": f"Bearer {trader_token}"},
                    data=payload
                )

                if follow_res.status == 200:
                    pass
                else:
                    err = follow_res.text()
                    if "already" in err.lower() or "unique" in err.lower():
                        print(f"[{i}/{args.end}] [INFO] {email} ({inst}) -> Already following")
                    else:
                        print(f"[{i}/{args.end}] [-] {email} ({inst}) -> {err}")
                        account_success = False

            if account_success:
                success_count += 1
                print(f"[{i}/{args.end}] [+] {email} is copying master on {target_instances}")

            acc_context.close()
            time.sleep(0.05)

        print("\n" + "=" * 75)
        print(f"[+] COMPLETED!")
        print(f"[+] Successfully followed: {success_count}/{total_followers} accounts")
        print("=" * 75)

        browser.close()


def main():
    parser = argparse.ArgumentParser(description="Playwright BlackTrader Copy Trading Follower")
    parser.add_argument("--url", default=BASE_URL, help="Base platform URL (default: from config/settings.py)")
    parser.add_argument("--prefix", default=DEFAULT_PREFIX, help="Follower email prefix (default: from config/settings.py)")
    parser.add_argument("--domain", default=DEFAULT_DOMAIN, help="Follower email domain (default: from config/settings.py)")
    parser.add_argument("--password", default=MEMBER_PASSWORD, help="Follower password (default: from config/settings.py)")
    parser.add_argument("--start", type=int, default=1, help="Starting index (default: 1)")
    parser.add_argument("--end", type=int, default=100, help="Ending index (default: 100)")
    parser.add_argument("--master", help="Target Master name or client ID ('mem_...')")
    parser.add_argument("--instance", choices=["paper", "real", "both"], default="paper", help="Trading instance (default: paper)")
    parser.add_argument("--method", choices=["multiplier", "balance", "equity"], default="multiplier", help="Copy sizing method")
    parser.add_argument("--multiplier", type=float, default=1.0, help="Lot size multiplier (default: 1.0)")
    parser.add_argument("--reverse", action="store_true", help="Reverse trade side (Buy -> Sell)")
    parser.add_argument("--copy-mode", choices=["public", "private"], default="public", help="Copy mode")
    parser.add_argument("--headed", action="store_true", help="Launch visible browser window")
    parser.add_argument("--slow-mo", type=int, default=0, help="Slow down Playwright actions by N ms")
    parser.add_argument("--list-masters", action="store_true", help="List available masters and exit")
    args = parser.parse_args()

    if args.list_masters:
        list_masters_playwright(args)
    else:
        if not args.master:
            print("[-] Error: --master is required. Pass a master name or ID, or run with --list-masters.")
            sys.exit(1)
        follow_master_playwright(args)


if __name__ == "__main__":
    main()

