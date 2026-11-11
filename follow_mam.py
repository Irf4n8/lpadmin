#!/usr/bin/env python3
"""
BlackTrader Bulk MAM Follow Script
===================================
Automates MAM follower accounts joining / following a MAM manager.

Flow:
1. Logs into each follower account (/api/auth/login).
2. Obtains a chart workspace token (/api/auth/chart-token).
3. Connects to the OMS MAM endpoint (/v1/oms/{instance}/mam/follow).
4. Sets the allocation method to 'multiplier' with multiplier 2.0 (or custom).

Usage:
    # 1. List all available MAM managers
    python follow_mam.py --list-masters

    # 2. Make mamfollower1 to mamfollower100 join mammaster with multiplier 2
    python follow_mam.py --master "mammaster" --multiplier 2.0 --start 1 --end 100

    # 3. Follow on both Paper and Real instances
    python follow_mam.py --master "mammaster" --instance both --multiplier 2.0 --start 1 --end 100
"""

import argparse
import sys
import time
import requests

DEFAULT_BASE_URL = "https://lpadmin.blackfx.com"
DEFAULT_MEMBER_PASSWORD = "Test@1234"
KNOWN_MAM_MASTERS = {
    "mammaster": "mem_e2dbce29e1c71a7bf6",
    "mammaster@mailinator.com": "mem_e2dbce29e1c71a7bf6"
}


class MamFollowerClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.chart_token = None

    def login(self, email: str, password: str) -> bool:
        """Authenticate follower trader and get session cookie."""
        url = f"{self.base_url}/api/auth/login"
        payload = {"email": email, "password": password}
        headers = {"Content-Type": "application/json"}

        try:
            resp = self.session.post(url, json=payload, headers=headers, timeout=15)
            if resp.status_code != 200:
                return False
            data = resp.json()
            return data.get("success", False)
        except Exception:
            return False

    def get_chart_token(self) -> str | None:
        """Mint workspace chart token."""
        url = f"{self.base_url}/api/auth/chart-token"
        headers = {"Content-Type": "application/json"}
        try:
            resp = self.session.post(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                return None
            data = resp.json()
            self.chart_token = data.get("token")
            return self.chart_token
        except Exception:
            return None

    def get_available_masters(self, instance: str = "paper") -> list:
        """Fetch list of MAM managers / masters."""
        if not self.chart_token:
            return []
        url = f"{self.base_url}/v1/oms/{instance}/mam/masters"
        headers = {
            "Authorization": f"Bearer {self.chart_token}",
            "Content-Type": "application/json"
        }
        try:
            resp = self.session.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                return resp.json().get("masters", [])
            # Fallback to copy masters endpoint if needed
            fallback_url = f"{self.base_url}/v1/oms/{instance}/copy/masters"
            fallback_resp = self.session.get(fallback_url, headers=headers, timeout=15)
            if fallback_resp.status_code == 200:
                return fallback_resp.json().get("masters", [])
            return []
        except Exception:
            return []

    def follow_master(
        self,
        master_client_id: str,
        instance: str = "paper",
        method: str = "multiplier",
        multiplier: float = 2.0,
        reverse: bool = False,
        copy_mode: str = "public"
    ) -> tuple[bool, str]:
        """Send follow / join request to MAM manager."""
        if not self.chart_token:
            return False, "No chart token available"

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

        # Try MAM endpoint first
        url = f"{self.base_url}/v1/oms/{instance}/mam/follow"
        try:
            resp = self.session.post(url, json=payload, headers=headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success") or data.get("status") == "ok":
                    return True, "Joined MAM manager successfully"
                return True, str(data)
            elif resp.status_code == 404:
                # If OMS handles both copy and mam via copy/follow endpoint
                copy_url = f"{self.base_url}/v1/oms/{instance}/copy/follow"
                c_resp = self.session.post(copy_url, json=payload, headers=headers, timeout=15)
                if c_resp.status_code == 200:
                    return True, "Joined manager successfully (via copy/follow)"
                return False, f"HTTP {c_resp.status_code}: {c_resp.text}"
            else:
                err = resp.json().get("error", resp.text) if resp.headers.get("content-type") == "application/json" else resp.text
                return False, f"HTTP {resp.status_code}: {err}"
        except Exception as e:
            return False, str(e)


def resolve_mam_master_id(client: MamFollowerClient, master_identifier: str, instance: str) -> str | None:
    """Find master client ID by name, known mapping, or direct ID."""
    if master_identifier.startswith("mem_"):
        return master_identifier

    # Check known mapping
    lower_ident = master_identifier.strip().lower()
    if lower_ident in KNOWN_MAM_MASTERS:
        return KNOWN_MAM_MASTERS[lower_ident]

    masters = client.get_available_masters(instance=instance)
    for m in masters:
        name = m.get("name", "").strip().lower()
        if name == lower_ident:
            return m.get("client_id")

    return None


def list_mam_masters(base_url: str, probe_email: str, probe_password: str, instance: str):
    """Probe the platform and display all registered MAM masters."""
    client = MamFollowerClient(base_url)
    print(f"[*] Logging in with probe account ({probe_email}) to fetch MAM masters...")
    if not client.login(probe_email, probe_password):
        print(f"[-] Failed to log in with {probe_email}. Ensure account exists and credentials match.")
        sys.exit(1)

    token = client.get_chart_token()
    if not token:
        print("[-] Could not retrieve chart token.")
        sys.exit(1)

    masters = client.get_available_masters(instance=instance)
    print("\n" + "=" * 85)
    print(f"{'MAM MASTER NAME':<22} | {'CLIENT ID':<26} | {'KIND':<16} | {'FOLLOWERS':<9}")
    print("-" * 85)
    if masters:
        for m in masters:
            name = m.get("name", "N/A")
            client_id = m.get("client_id", "N/A")
            kind = m.get("kind", "N/A")
            followers = m.get("stats", {}).get("followers", 0)
            print(f"{name:<22} | {client_id:<26} | {kind:<16} | {followers:<9}")
    else:
        print(f"[-] No registered masters returned by endpoint. Known master: mammaster ({KNOWN_MAM_MASTERS['mammaster']})")
    print("=" * 85 + "\n")


def main():
    parser = argparse.ArgumentParser(description="BlackTrader Bulk MAM Follow Script")
    parser.add_argument("--url", default=DEFAULT_BASE_URL, help="Base platform URL")
    parser.add_argument("--prefix", default="mamfollower", help="Follower email prefix (default: mamfollower)")
    parser.add_argument("--domain", default="mailinator.com", help="Follower email domain (default: mailinator.com)")
    parser.add_argument("--password", default=DEFAULT_MEMBER_PASSWORD, help="Follower account password")
    parser.add_argument("--start", type=int, default=1, help="Starting follower index (default: 1)")
    parser.add_argument("--end", type=int, default=100, help="Ending follower index (default: 100)")
    parser.add_argument("--master", default="mammaster", help="Target MAM master name (default: mammaster) or client ID")
    parser.add_argument("--instance", choices=["paper", "real", "both"], default="paper", help="Trading instance (default: paper)")
    parser.add_argument("--method", choices=["multiplier", "balance", "equity"], default="multiplier", help="Allocation sizing method")
    parser.add_argument("--multiplier", type=float, default=2.0, help="Lot size multiplier (default: 2.0)")
    parser.add_argument("--reverse", action="store_true", help="Trade opposite side (buy -> sell)")
    parser.add_argument("--copy-mode", choices=["public", "private"], default="public", help="Copy mode")
    parser.add_argument("--list-masters", action="store_true", help="List all available MAM masters and exit")
    args = parser.parse_args()

    probe_email = f"{args.prefix}{args.start}@{args.domain}"

    # Mode 1: List masters
    if args.list_masters:
        inst = "paper" if args.instance == "both" else args.instance
        list_mam_masters(args.url, probe_email, args.password, inst)
        return

    # Mode 2: Resolve master client ID
    probe_client = MamFollowerClient(args.url)
    if not probe_client.login(probe_email, args.password):
        print(f"[-] Could not login with initial account {probe_email}. Check credentials.")
        sys.exit(1)
    probe_client.get_chart_token()

    inst_for_lookup = "paper" if args.instance == "both" else args.instance
    target_master_id = resolve_mam_master_id(probe_client, args.master, inst_for_lookup)

    if not target_master_id:
        print(f"[-] Could not find any master matching '{args.master}'. Run with --list-masters to see valid names.")
        sys.exit(1)

    target_instances = ["paper", "real"] if args.instance == "both" else [args.instance]
    total_followers = args.end - args.start + 1

    print("\n" + "=" * 75)
    print(f"[*] Bulk MAM Follow Task")
    print(f"[*] Target MAM Master  : {args.master} (ID: {target_master_id})")
    print(f"[*] Follower Accounts  : {args.prefix}{args.start}@{args.domain} -> {args.prefix}{args.end}@{args.domain} ({total_followers} total)")
    print(f"[*] Instances          : {', '.join(target_instances)}")
    print(f"[*] Sizing Method      : {args.method} (Multiplier: {args.multiplier})")
    print(f"[*] Reverse Trading    : {args.reverse}")
    print("=" * 75 + "\n")

    success_count = 0

    for i in range(args.start, args.end + 1):
        email = f"{args.prefix}{i}@{args.domain}"
        client = MamFollowerClient(args.url)

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
            else:
                print(f"[{i}/{args.end}] [+] {email} ({inst}) -> {msg}")

        if account_ok:
            success_count += 1

        time.sleep(0.05)

    print("\n" + "=" * 75)
    print(f"[+] Task Finished!")
    print(f"[+] Successfully followed: {success_count}/{total_followers} accounts")
    print("=" * 75)


if __name__ == "__main__":
    main()

