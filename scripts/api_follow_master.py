#!/usr/bin/env python3
"""
Direct HTTP API Copy Trading Follow Script
===========================================
Lightweight script using requests to make follower accounts follow a master trader.
Settings and credentials are read from config.settings (.env).

Usage:
    python scripts/api_follow_master.py --list-masters
    python scripts/api_follow_master.py --master "ctmaster" --start 1 --end 100
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
import requests


class FollowerClient:
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.chart_token = None

    def login(self, email: str, password: str) -> bool:
        """Authenticate follower trader and get session cookie."""
        url = f"{self.base_url}/api/auth/login"
        payload = {"email": email, "password": password}
        headers = {"Content-Type": "application/json"}

        resp = self.session.post(url, json=payload, headers=headers, timeout=15)
        if resp.status_code != 200:
            return False
        return resp.json().get("success", False)

    def get_chart_token(self) -> str | None:
        """Mint workspace chart token."""
        url = f"{self.base_url}/api/auth/chart-token"
        headers = {"Content-Type": "application/json"}
        resp = self.session.post(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return None
        self.chart_token = resp.json().get("token")
        return self.chart_token

    def get_available_masters(self, instance: str = "paper") -> list:
        """Fetch list of copy-trade masters."""
        if not self.chart_token:
            return []
        url = f"{self.base_url}/v1/oms/{instance}/copy/masters"
        headers = {
            "Authorization": f"Bearer {self.chart_token}",
            "Content-Type": "application/json"
        }
        resp = self.session.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return []
        return resp.json().get("masters", [])

    def follow_master(
        self,
        master_client_id: str,
        instance: str = "paper",
        method: str = "multiplier",
        multiplier: float = 1.0,
        reverse: bool = False,
        copy_mode: str = "public"
    ) -> tuple[bool, str]:
        """Send follow request to copy master trades."""
        if not self.chart_token:
            return False, "No chart token available"

        url = f"{self.base_url}/v1/oms/{instance}/copy/follow"
        headers = {
            "Authorization": f"Bearer {self.chart_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "master_client_id": master_client_id,
            "method": method,
            "multiplier": multiplier,
            "reverse": reverse,
            "copy_mode": copy_mode
        }
        resp = self.session.post(url, json=payload, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success"):
                return True, "Followed successfully"
            return False, str(data)
        elif resp.status_code == 400:
            err = resp.json().get("error", resp.text)
            return False, f"HTTP 400: {err}"
        else:
            return False, f"HTTP {resp.status_code}: {resp.text}"


def list_masters(base_url: str, probe_email: str, probe_password: str, instance: str):
    """Probe the platform and display all registered copy masters."""
    client = FollowerClient(base_url)
    print(f"[*] Logging in with probe account ({probe_email}) to fetch masters...")
    if not client.login(probe_email, probe_password):
        print(f"[-] Failed to log in with {probe_email}. Ensure account exists and credentials match.")
        sys.exit(1)

    token = client.get_chart_token()
    if not token:
        print("[-] Could not retrieve chart token.")
        sys.exit(1)

    masters = client.get_available_masters(instance=instance)
    if not masters:
        print(f"[-] No masters found on instance '{instance}'.")
        return

    print("\n" + "=" * 85)
    print(f"{'MASTER NAME':<22} | {'CLIENT ID':<26} | {'KIND':<16} | {'FOLLOWERS':<9} | {'GROWTH'}")
    print("-" * 85)
    for m in masters:
        name = m.get("name", "N/A")
        client_id = m.get("client_id", "N/A")
        kind = m.get("kind", "N/A")
        stats = m.get("stats", {})
        followers = stats.get("followers", 0)
        growth = stats.get("growth", 0)
        print(f"{name:<22} | {client_id:<26} | {kind:<16} | {followers:<9} | {growth}")
    print("=" * 85 + "\n")


def resolve_master_id(client: FollowerClient, master_identifier: str, instance: str) -> str | None:
    """Find master client ID by name or direct ID."""
    if master_identifier.startswith("mem_"):
        return master_identifier

    masters = client.get_available_masters(instance=instance)
    for m in masters:
        if m.get("name", "").strip().lower() == master_identifier.strip().lower():
            return m.get("client_id")

    return None


def main():
    parser = argparse.ArgumentParser(description="Direct HTTP API BlackTrader Copy Trading Follower")
    parser.add_argument("--url", default=BASE_URL, help="Base platform URL (default: from config/settings.py)")
    parser.add_argument("--prefix", default=DEFAULT_PREFIX, help="Follower email prefix (default: from config/settings.py)")
    parser.add_argument("--domain", default=DEFAULT_DOMAIN, help="Follower email domain (default: from config/settings.py)")
    parser.add_argument("--password", default=MEMBER_PASSWORD, help="Follower password (default: from config/settings.py)")
    parser.add_argument("--start", type=int, default=1, help="Starting follower index (default: 1)")
    parser.add_argument("--end", type=int, default=100, help="Ending follower index (default: 100)")
    parser.add_argument("--master", help="Target Master name or client ID ('mem_...')")
    parser.add_argument("--instance", choices=["paper", "real", "both"], default="paper", help="Trading instance (default: paper)")
    parser.add_argument("--method", choices=["multiplier", "balance", "equity"], default="multiplier", help="Copy sizing method")
    parser.add_argument("--multiplier", type=float, default=1.0, help="Lot size multiplier (default: 1.0)")
    parser.add_argument("--reverse", action="store_true", help="Trade opposite side (buy -> sell)")
    parser.add_argument("--copy-mode", choices=["public", "private"], default="public", help="Copy mode")
    parser.add_argument("--list-masters", action="store_true", help="List all available copy masters and exit")
    args = parser.parse_args()

    if not args.password:
        print("[-] Error: Follower password missing. Configure MEMBER_PASSWORD in .env or pass --password.")
        sys.exit(1)

    probe_email = f"{args.prefix}{args.start}@{args.domain}"

    if args.list_masters:
        inst = "paper" if args.instance == "both" else args.instance
        list_masters(args.url, probe_email, args.password, inst)
        return

    if not args.master:
        print("[-] Error: --master is required. Pass a master name or ID, or use --list-masters to view available masters.")
        sys.exit(1)

    probe_client = FollowerClient(args.url)
    if not probe_client.login(probe_email, args.password):
        print(f"[-] Could not login with initial account {probe_email}. Check credentials.")
        sys.exit(1)
    probe_client.get_chart_token()

    inst_for_lookup = "paper" if args.instance == "both" else args.instance
    target_master_id = resolve_master_id(probe_client, args.master, inst_for_lookup)

    if not target_master_id:
        print(f"[-] Could not find any master matching '{args.master}'. Run with --list-masters to see valid names.")
        sys.exit(1)

    target_instances = ["paper", "real"] if args.instance == "both" else [args.instance]
    total_followers = args.end - args.start + 1

    print("\n" + "=" * 75)
    print(f"[*] Bulk Copy-Trading Follow Task")
    print(f"[*] Target Master      : {args.master} (ID: {target_master_id})")
    print(f"[*] Follower Accounts  : {args.prefix}{args.start}@{args.domain} -> {args.prefix}{args.end}@{args.domain} ({total_followers} total)")
    print(f"[*] Instances          : {', '.join(target_instances)}")
    print(f"[*] Sizing Method      : {args.method} (Multiplier: {args.multiplier})")
    print(f"[*] Reverse Trading    : {args.reverse}")
    print("=" * 75 + "\n")

    success_count = 0

    for i in range(args.start, args.end + 1):
        email = f"{args.prefix}{i}@{args.domain}"
        client = FollowerClient(args.url)

        if not client.login(email, args.password):
            print(f"[{i}/{args.end}] [-] Login failed for {email}")
            continue

        token = client.get_chart_token()
        if not token:
            print(f"[{i}/{args.end}] [-] Failed to get chart token for {email}")
            continue

        account_ok = True
        for inst in target_instances:
            ok, msg = client.follow_master(
                master_client_id=target_master_id,
                instance=inst,
                method=args.method,
                multiplier=args.multiplier,
                reverse=args.reverse,
                copy_mode=args.copy_mode
            )
            if not ok:
                if "already" in msg.lower() or "unique" in msg.lower():
                    print(f"[{i}/{args.end}] [INFO] {email} ({inst}) -> Already following")
                else:
                    print(f"[{i}/{args.end}] [-] {email} ({inst}) -> {msg}")
                    account_ok = False

        if account_ok:
            success_count += 1
            print(f"[{i}/{args.end}] [+] {email} is now copying master on {target_instances}")

        time.sleep(0.05)

    print("\n" + "=" * 75)
    print(f"[+] Task Finished!")
    print(f"[+] Successfully followed: {success_count}/{total_followers} accounts")
    print("=" * 75)


if __name__ == "__main__":
    main()

