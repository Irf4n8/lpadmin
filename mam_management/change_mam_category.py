#!/usr/bin/env python3
"""
Single Unified MAM Category Manager
====================================
Dynamically switches follower accounts to any MAM category:
  1. Multiplier (e.g., 2.0x, 1.5x)
  2. Equity Based (proportional to follower/master equity)
  3. Balance Based (proportional to follower/master balance)

Features:
- Dynamic Master: Provide any master email or client_id (defaults to .env MAM_MASTER).
- Dynamic Followers:
    * Range: --start 1 --end 100 (using prefix & domain)
    * List:  --followers "acc1@mail.com,acc2@mail.com"
    * File:  --file accounts.txt
- Auto-Unfollow: Leaves existing follow link cleanly before establishing new configuration.
- Concurrency: Multi-threaded execution across accounts for rapid completion.
- Verification: Validates active follow status directly against OMS API.

Usage:
    # 1. Switch all 100 followers to Multiplier (2.0x)
    python mam_management/change_mam_category.py --category multiplier --multiplier 2.0

    # 2. Switch all 100 followers to Equity Based
    python mam_management/change_mam_category.py --category equity

    # 3. Switch all 100 followers to Balance Based
    python mam_management/change_mam_category.py --category balance

    # 4. Target custom master or specific follower accounts
    python mam_management/change_mam_category.py --master "newmaster@test.com" --followers "trader1@test.com,trader2@test.com" --category multiplier --multiplier 3.0
"""

import os
import sys
import time
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Tuple, Optional
import requests

# Load environment configuration if available
ENV_PATH = Path(".env")
CONFIG = {
    "BASE_URL": "https://lpadmin.blackfx.com",
    "MAM_MASTER": "mammaster@mailinator.com",
    "FOLLOWERS_PASSWORD": "Test@1234",
    "PREFIX": "mamfollower",
    "DOMAIN": "mailinator.com",
    "START": 1,
    "END": 100,
    "INSTANCE": "paper"
}

if ENV_PATH.exists():
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k == "BASE_URL":
                    CONFIG["BASE_URL"] = v
                elif k == "MAM_MASTER":
                    CONFIG["MAM_MASTER"] = v
                elif k == "FOLLOWERS_PASSWORD":
                    CONFIG["FOLLOWERS_PASSWORD"] = v
                elif k == "DEFAULT_EMAIL_PREFIX":
                    CONFIG["PREFIX"] = v
                elif k == "DEFAULT_EMAIL_DOMAIN":
                    CONFIG["DOMAIN"] = v

KNOWN_MASTERS = {
    "mammaster": "mem_e2dbce29e1c71a7bf6",
    "mammaster@mailinator.com": "mem_e2dbce29e1c71a7bf6"
}


class MamTraderSession:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.chart_token: Optional[str] = None
        self.client_id: Optional[str] = None

    def login(self, email: str, password: str) -> bool:
        """Authenticate user and obtain session cookie."""
        url = f"{self.base_url}/api/auth/login"
        payload = {"email": email, "password": password}
        try:
            resp = self.session.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                self.client_id = data.get("client_id")
                return data.get("success", False)
            return False
        except Exception:
            return False

    def get_chart_token(self) -> Optional[str]:
        """Obtain chart token required for OMS endpoints."""
        url = f"{self.base_url}/api/auth/chart-token"
        try:
            resp = self.session.post(url, headers={"Content-Type": "application/json"}, timeout=12)
            if resp.status_code == 200:
                self.chart_token = resp.json().get("token")
                return self.chart_token
            return None
        except Exception:
            return None

    def get_masters(self, instance: str = "paper") -> List[Dict[str, Any]]:
        """Query available MAM masters on OMS."""
        if not self.chart_token:
            return []
        headers = {"Authorization": f"Bearer {self.chart_token}"}
        url = f"{self.base_url}/v1/oms/{instance}/mam/masters"
        try:
            resp = self.session.get(url, headers=headers, timeout=12)
            if resp.status_code == 200:
                return resp.json().get("masters", [])
            # fallback to copy
            resp2 = self.session.get(f"{self.base_url}/v1/oms/{instance}/copy/masters", headers=headers, timeout=12)
            if resp2.status_code == 200:
                return resp2.json().get("masters", [])
            return []
        except Exception:
            return []

    def get_active_follows(self, instance: str = "paper") -> List[Dict[str, Any]]:
        """Fetch current follower subscriptions."""
        if not self.chart_token:
            return []
        headers = {"Authorization": f"Bearer {self.chart_token}"}
        url = f"{self.base_url}/v1/oms/{instance}/mam/follows"
        try:
            resp = self.session.get(url, headers=headers, timeout=12)
            if resp.status_code == 200:
                return [f for f in resp.json().get("following", []) if f.get("status") == "active"]
            return []
        except Exception:
            return []

    def unfollow_master(self, master_client_id: str, follow_id: Optional[str] = None, instance: str = "paper") -> Tuple[bool, str]:
        """Leave / unfollow MAM master."""
        if not self.chart_token:
            return False, "Missing chart token"
        headers = {"Authorization": f"Bearer {self.chart_token}", "Content-Type": "application/json"}
        payload = {"master_client_id": master_client_id}
        if follow_id:
            payload["follow_id"] = follow_id

        url = f"{self.base_url}/v1/oms/{instance}/mam/unfollow"
        try:
            resp = self.session.post(url, json=payload, headers=headers, timeout=12)
            if resp.status_code == 200:
                return True, "Unfollowed successfully"
            elif resp.status_code == 404:
                # Fallback to copy unfollow
                c_resp = self.session.post(f"{self.base_url}/v1/oms/{instance}/copy/unfollow", json=payload, headers=headers, timeout=12)
                if c_resp.status_code == 200:
                    return True, "Unfollowed (copy)"
                return False, f"HTTP {c_resp.status_code}"
            return False, f"HTTP {resp.status_code}: {resp.text}"
        except Exception as e:
            return False, str(e)

    def follow_master(
        self,
        master_client_id: str,
        method: str,
        multiplier: float = 1.0,
        share_percent: float = 50.0,
        instance: str = "paper"
    ) -> Tuple[bool, str]:
        """Join MAM master in specified category."""
        if not self.chart_token:
            return False, "Missing chart token"
        headers = {"Authorization": f"Bearer {self.chart_token}", "Content-Type": "application/json"}
        payload = {
            "master_client_id": master_client_id,
            "method": method,
            "multiplier": multiplier,
            "share_percent": share_percent,
            "reverse": False,
            "copy_mode": "public"
        }
        url = f"{self.base_url}/v1/oms/{instance}/mam/follow"
        try:
            resp = self.session.post(url, json=payload, headers=headers, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success") or data.get("status") == "ok":
                    return True, "Joined"
                return True, str(data)
            elif resp.status_code == 404:
                # Fallback copy follow
                c_resp = self.session.post(f"{self.base_url}/v1/oms/{instance}/copy/follow", json=payload, headers=headers, timeout=12)
                if c_resp.status_code == 200:
                    return True, "Joined (copy)"
                return False, f"HTTP {c_resp.status_code}: {c_resp.text}"
            return False, f"HTTP {resp.status_code}: {resp.text}"
        except Exception as e:
            return False, str(e)


def resolve_master_id(probe_session: MamTraderSession, master_ident: str, instance: str) -> Optional[str]:
    """Dynamically resolve master email or ID to OMS client_id."""
    if master_ident.startswith("mem_"):
        return master_ident

    low = master_ident.strip().lower()
    if low in KNOWN_MASTERS:
        return KNOWN_MASTERS[low]

    masters = probe_session.get_masters(instance=instance)
    for m in masters:
        name = m.get("name", "").strip().lower()
        cid = m.get("client_id")
        email = m.get("email", "").strip().lower()
        if low in [name, email, cid]:
            return cid
    return None


def switch_follower_category(
    email: str,
    password: str,
    master_client_id: str,
    target_category: str,
    multiplier: float,
    share_percent: float,
    instance: str,
    base_url: str
) -> Dict[str, Any]:
    """Unfollows existing master link if present and re-follows with target category."""
    trader = MamTraderSession(base_url)
    if not trader.login(email, password):
        return {"email": email, "success": False, "reason": "Login authentication failed"}

    token = trader.get_chart_token()
    if not token:
        return {"email": email, "success": False, "reason": "Failed to mint chart token"}

    # 1. Inspect existing active follows
    active_follows = trader.get_active_follows(instance=instance)
    old_mode = "None"
    for f in active_follows:
        if f.get("master_client_id") == master_client_id:
            old_mode = f"{f.get('method')} ({f.get('multiplier')}x)"
            # Unfollow cleanly
            trader.unfollow_master(master_client_id, follow_id=f.get("follow_id"), instance=instance)
            break

    # 2. Join under new category
    ok, msg = trader.follow_master(
        master_client_id=master_client_id,
        method=target_category,
        multiplier=multiplier,
        share_percent=share_percent,
        instance=instance
    )

    if not ok:
        return {"email": email, "success": False, "reason": f"Follow failed: {msg}", "old_mode": old_mode}

    # 3. Verify new active state
    new_follows = trader.get_active_follows(instance=instance)
    verified = False
    active_entry = None
    for nf in new_follows:
        if nf.get("master_client_id") == master_client_id:
            verified = (nf.get("method") == target_category)
            active_entry = nf
            break

    return {
        "email": email,
        "success": verified,
        "old_mode": old_mode,
        "new_mode": f"{target_category} ({multiplier}x)" if target_category == "multiplier" else target_category,
        "verified": verified,
        "detail": active_entry
    }


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Unified MAM Category Manager: Switch followers to multiplier, equity, or balance."
    )
    # Category selection
    parser.add_argument(
        "--category", "--mode",
        choices=["multiplier", "equity", "balance", "equity-based", "balance-based", "multiplier-based"],
        required=True,
        help="Target allocation category (multiplier, equity, or balance)"
    )
    parser.add_argument(
        "--multiplier",
        type=float,
        default=2.0,
        help="Multiplier factor when category is multiplier (default: 2.0)"
    )
    parser.add_argument(
        "--share-percent",
        type=float,
        default=50.0,
        help="MAM manager profit share percentage (default: 50.0%%)"
    )

    # Dynamic Master
    parser.add_argument(
        "--master",
        default=CONFIG["MAM_MASTER"],
        help=f"Master email or client_id (default: {CONFIG['MAM_MASTER']})"
    )

    # Dynamic Followers
    parser.add_argument(
        "--followers",
        default=None,
        help="Comma-separated list of follower emails"
    )
    parser.add_argument(
        "--file",
        default=None,
        help="Path to text file containing follower emails (one per line)"
    )
    parser.add_argument(
        "--start",
        type=int,
        default=CONFIG["START"],
        help=f"Follower range start index (default: {CONFIG['START']})"
    )
    parser.add_argument(
        "--end",
        type=int,
        default=CONFIG["END"],
        help=f"Follower range end index (default: {CONFIG['END']})"
    )
    parser.add_argument(
        "--prefix",
        default=CONFIG["PREFIX"],
        help=f"Follower email prefix (default: {CONFIG['PREFIX']})"
    )
    parser.add_argument(
        "--domain",
        default=CONFIG["DOMAIN"],
        help=f"Follower email domain (default: {CONFIG['DOMAIN']})"
    )
    parser.add_argument(
        "--password",
        default=CONFIG["FOLLOWERS_PASSWORD"],
        help="Follower account password"
    )

    # General configuration
    parser.add_argument(
        "--instance",
        choices=["paper", "real"],
        default=CONFIG["INSTANCE"],
        help=f"Trading instance (default: {CONFIG['INSTANCE']})"
    )
    parser.add_argument(
        "--url",
        default=CONFIG["BASE_URL"],
        help=f"BlackTrader base URL (default: {CONFIG['BASE_URL']})"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=20,
        help="Concurrent worker threads (default: 20)"
    )
    return parser.parse_args()


def main():
    args = parse_arguments()

    # Normalize category name
    cat_map = {
        "multiplier": "multiplier",
        "multiplier-based": "multiplier",
        "equity": "equity",
        "equity-based": "equity",
        "balance": "balance",
        "balance-based": "balance"
    }
    target_category = cat_map[args.category.lower()]

    # Assemble follower emails dynamically
    follower_emails: List[str] = []
    if args.followers:
        follower_emails = [e.strip() for e in args.followers.split(",") if e.strip()]
    elif args.file:
        fpath = Path(args.file)
        if not fpath.exists():
            print(f"[-] Accounts file not found: {args.file}")
            sys.exit(1)
        with open(fpath, "r", encoding="utf-8") as f:
            follower_emails = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    else:
        for i in range(args.start, args.end + 1):
            follower_emails.append(f"{args.prefix}{i}@{args.domain}")

    if not follower_emails:
        print("[-] No follower accounts specified.")
        sys.exit(1)

    print("\n" + "=" * 80)
    print("                 UNIFIED MAM CATEGORY MANAGER")
    print("=" * 80)
    print(f"[*] Target Category   : {target_category.upper()}")
    if target_category == "multiplier":
        print(f"[*] Multiplier Factor : {args.multiplier}x")
    print(f"[*] Profit Share      : {args.share_percent}%")
    print(f"[*] Trading Instance  : {args.instance.upper()}")
    print(f"[*] Target Master     : {args.master}")
    print(f"[*] Total Followers   : {len(follower_emails)} accounts")
    print(f"[*] Concurrency       : {args.workers} threads")
    print("=" * 80 + "\n")

    # Resolve master ID using a probe session
    probe = MamTraderSession(args.url)
    probe_user = follower_emails[0]
    if not probe.login(probe_user, args.password):
        print(f"[-] Probe account login failed: {probe_user}")
        sys.exit(1)
    probe.get_chart_token()

    master_client_id = resolve_master_id(probe, args.master, args.instance)
    if not master_client_id:
        print(f"[-] Could not resolve master client ID for '{args.master}'.")
        sys.exit(1)

    print(f"[+] Resolved Master Client ID: {master_client_id}\n")
    print("[*] Switching follower categories across fleet...")

    start_t = time.time()
    results = []

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_email = {
            executor.submit(
                switch_follower_category,
                em,
                args.password,
                master_client_id,
                target_category,
                args.multiplier,
                args.share_percent,
                args.instance,
                args.url
            ): em
            for em in follower_emails
        }

        completed = 0
        for fut in as_completed(future_to_email):
            res = fut.result()
            results.append(res)
            completed += 1
            tag = "[+]" if res.get("success") else "[-]"
            old_str = res.get("old_mode", "N/A")
            new_str = res.get("new_mode", res.get("reason", "Failed"))
            print(f"[{completed:3d}/{len(follower_emails)}] {tag} {res['email']:<32} | {old_str:<16} -> {new_str}")

    elapsed = time.time() - start_t
    success_count = sum(1 for r in results if r.get("success"))

    print("\n" + "=" * 80)
    print(f"[+] SUMMARY: Successfully updated {success_count}/{len(follower_emails)} accounts in {elapsed:.2f}s")
    print(f"[+] Active Category: {target_category.upper()}")
    print("=" * 80 + "\n")

    if success_count < len(follower_emails):
        failed = [r for r in results if not r.get("success")]
        print("[-] Failed accounts summary:")
        for fa in failed[:10]:
            print(f"    - {fa['email']}: {fa.get('reason')}")
        if len(failed) > 10:
            print(f"    ... and {len(failed) - 10} more.")
        sys.exit(1)


if __name__ == "__main__":
    main()
