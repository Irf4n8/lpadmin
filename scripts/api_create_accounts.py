#!/usr/bin/env python3
"""
Direct HTTP API Member Account Creation & Balance Funding
=========================================================
Lightweight script using requests to bulk-create accounts and set balances.
Settings and credentials are read from config.settings (.env).

Usage:
    python scripts/api_create_accounts.py --start 1 --end 100
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
import requests


class BlackTraderAdmin:
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.token = None

    def login(self, email: str, password: str) -> bool:
        """Authenticate with the admin API and obtain a bearer token."""
        url = f"{self.base_url}/admin/api/login"
        payload = {"email": email, "password": password, "remember": True}
        headers = {"Content-Type": "application/json"}

        print(f"[*] Logging in as admin ({email})...")
        resp = self.session.post(url, json=payload, headers=headers, timeout=15)
        if resp.status_code != 200:
            print(f"[-] Login failed: HTTP {resp.status_code} - {resp.text}")
            return False

        data = resp.json()
        self.token = data.get("token")
        if not self.token:
            print(f"[-] No token returned in login response: {data}")
            return False

        self.session.headers.update({
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        })
        print(f"[+] Admin logged in successfully! (Client #{data.get('client_id', 'N/A')})")
        return True

    def get_existing_members(self) -> dict:
        """Retrieve existing members indexed by email."""
        url = f"{self.base_url}/admin/api/members"
        resp = self.session.get(url, timeout=20)
        if resp.status_code != 200:
            print(f"[-] Failed to fetch members: HTTP {resp.status_code}")
            return {}
        data = resp.json()
        members = data.get("members", [])
        return {m.get("email"): m for m in members if "email" in m}

    def create_member(self, email: str, password: str, name: str = "") -> dict | None:
        """Create a new member account."""
        url = f"{self.base_url}/admin/api/members"
        payload = {"email": email, "password": password, "name": name}
        resp = self.session.post(url, json=payload, timeout=15)
        if resp.status_code != 200:
            print(f"[-] Failed to create {email}: HTTP {resp.status_code} - {resp.text}")
            return None
        return resp.json().get("member")

    def set_balance(self, member_id: str, balance: float, instance: str = "paper") -> bool:
        """Set account balance for paper or real instance."""
        url = f"{self.base_url}/admin/api/members/{member_id}/balance"
        payload = {
            "instance": instance,
            "balance": balance,
            "remark": f"Bulk script funding ({instance})",
            "force": True
        }
        resp = self.session.post(url, json=payload, timeout=15)
        if resp.status_code != 200:
            print(f"[-] Failed to set {instance} balance for {member_id}: HTTP {resp.status_code} - {resp.text}")
            return False
        return True


def main():
    parser = argparse.ArgumentParser(description="Direct HTTP API BlackTrader Account Creator")
    parser.add_argument("--url", default=BASE_URL, help="Base admin URL (default: from config/settings.py)")
    parser.add_argument("--admin-email", default=ADMIN_EMAIL, help="Admin login email (default: from config/settings.py)")
    parser.add_argument("--admin-pass", default=ADMIN_PASSWORD, help="Admin login password (default: from config/settings.py)")
    parser.add_argument("--prefix", default=DEFAULT_PREFIX, help="Email prefix (default: from config/settings.py)")
    parser.add_argument("--domain", default=DEFAULT_DOMAIN, help="Email domain (default: from config/settings.py)")
    parser.add_argument("--member-pass", default=MEMBER_PASSWORD, help="Password for members (default: from config/settings.py)")
    parser.add_argument("--start", type=int, default=1, help="Starting index (default: 1)")
    parser.add_argument("--end", type=int, default=100, help="Ending index (default: 100)")
    parser.add_argument("--balance", type=float, default=DEFAULT_BALANCE, help="Balance per account (default: from config/settings.py)")
    parser.add_argument("--instances", default=DEFAULT_INSTANCES, help="Comma-separated instances: paper,real")
    args = parser.parse_args()

    if not args.admin_email or not args.admin_pass:
        print("[-] Error: Admin credentials missing. Configure ADMIN_EMAIL and ADMIN_PASSWORD in .env or pass via CLI.")
        sys.exit(1)

    instances = [i.strip() for i in args.instances.split(",") if i.strip()]

    admin = BlackTraderAdmin(base_url=args.url)
    if not admin.login(args.admin_email, args.admin_pass):
        sys.exit(1)

    print("[*] Fetching existing members to avoid duplicate creations...")
    existing = admin.get_existing_members()
    print(f"[+] Total existing members on platform: {len(existing)}")

    total_to_process = args.end - args.start + 1
    print(f"\n[*] Starting creation/funding of {total_to_process} accounts: {args.prefix}{args.start}@{args.domain} -> {args.prefix}{args.end}@{args.domain}")
    print(f"[*] Target balance: {args.balance:,.2f} on instances: {', '.join(instances)}")
    print("-" * 70)

    created_count = 0
    funded_count = 0

    for i in range(args.start, args.end + 1):
        email = f"{args.prefix}{i}@{args.domain}"
        member_id = None

        if email in existing:
            member = existing[email]
            member_id = member.get("member_id")
            print(f"[{i}/{args.end}] {email} already exists (ID: {member_id}). Checking balance...")
        else:
            member = admin.create_member(email=email, password=args.member_pass, name="")
            if member:
                member_id = member.get("member_id")
                created_count += 1
                print(f"[{i}/{args.end}] [CREATED] {email} -> ID: {member_id}")
            else:
                print(f"[{i}/{args.end}] [SKIP] Could not create {email}")
                continue

        if member_id:
            bal_ok = True
            for inst in instances:
                if not admin.set_balance(member_id, args.balance, instance=inst):
                    bal_ok = False
            if bal_ok:
                funded_count += 1
                print(f"         [FUNDED] {args.balance:,.2f} set on {instances}")

        time.sleep(0.05)

    print("\n" + "=" * 70)
    print(f"[+] DONE!")
    print(f"[+] New accounts created : {created_count}")
    print(f"[+] Accounts funded      : {funded_count}/{total_to_process}")
    print("=" * 70)


if __name__ == "__main__":
    main()

