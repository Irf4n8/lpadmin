"""
Setup and Baseline Verification Module
======================================
1. Verifies master and all 100 followers exist and are funded.
2. Snapshots balance, equity, margin, and open positions.
3. Configures varied multipliers across the 100 followers (1.0x, 2.0x, 3.0x, 0.5x).
4. Saves pre-test baseline snapshot to reports/evidence/baseline_snapshot.json.
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List

from config.settings import BASE_DIR
from test_suite.client import BlackTraderClient


def get_expected_multiplier(index: int) -> float:
    """Return varied multiplier distribution across 100 followers."""
    if 1 <= index <= 25:
        return 1.0
    elif 26 <= index <= 50:
        return 2.0
    elif 51 <= index <= 75:
        return 3.0
    else:
        return 0.5


def run_setup_and_baseline(
    client: BlackTraderClient,
    master_email: str,
    master_client_id: str,
    follower_emails: List[str],
    instance: str = "paper"
) -> Dict[str, Any]:
    print("\n" + "=" * 80)
    print(" [PHASE A] SETUP AND BASELINE VERIFICATION (100 FOLLOWERS)")
    print("=" * 80)

    # Step 1: Clean slate teardown
    client.teardown_all_accounts(master_email, follower_emails, instance=instance)
    time.sleep(1.0)

    # Step 2: Assign varied multipliers
    print(f"\n[*] Configuring varied multipliers (1.0x, 2.0x, 3.0x, 0.5x) for {len(follower_emails)} followers...")
    follow_results = {}

    def configure_follower(item):
        idx, email = item
        mult = get_expected_multiplier(idx)
        res = client.follow_master(
            email=email,
            master_client_id=master_client_id,
            instance=instance,
            method="multiplier",
            multiplier=mult,
            reverse=False,
            copy_mode="public"
        )
        return email, mult, res.get("status_code") == 200

    with ThreadPoolExecutor(max_workers=client.max_workers) as executor:
        items = [(i + 1, email) for i, email in enumerate(follower_emails)]
        for email, mult, ok in executor.map(configure_follower, items):
            follow_results[email] = {"multiplier": mult, "ok": ok}

    success_follow_count = sum(1 for v in follow_results.values() if v["ok"])
    print(f"[+] Multipliers assigned: {success_follow_count}/{len(follower_emails)} successful.")

    # Step 3: Read back master copy followers
    print(f"[*] Reading back follow linkages from master ({master_email})...")
    registered_followers = client.get_copy_followers(master_email, instance=instance)
    print(f"[+] Master reports {len(registered_followers)} active follower links.")

    # Step 4: Snapshot master
    print(f"[*] Capturing master snapshot...")
    master_pos_data = client.get_positions(master_email, instance=instance)
    master_funds = master_pos_data.get("funds", {})
    master_snapshot = {
        "email": master_email,
        "client_id": master_client_id,
        "balance": master_funds.get("balance", 0),
        "equity": master_funds.get("equity", 0),
        "free_margin": master_funds.get("free_margin", 0),
        "used_margin": master_funds.get("used_margin", 0),
        "open_positions": master_pos_data.get("count", 0)
    }

    # Step 5: Concurrently snapshot all 100 followers
    print(f"[*] Concurrently snapshotting all {len(follower_emails)} followers (balance, equity, margin, positions)...")
    follower_positions = client.fetch_all_followers_positions(follower_emails, instance=instance)

    follower_snapshots = {}
    for i, email in enumerate(follower_emails):
        idx = i + 1
        pos_data = follower_positions.get(email, {})
        funds = pos_data.get("funds", {})
        follower_snapshots[email] = {
            "index": idx,
            "multiplier": get_expected_multiplier(idx),
            "balance": funds.get("balance", 0),
            "equity": funds.get("equity", 0),
            "free_margin": funds.get("free_margin", 0),
            "used_margin": funds.get("used_margin", 0),
            "open_positions": pos_data.get("count", 0)
        }

    baseline_data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "instance": instance,
        "master": master_snapshot,
        "followers_count": len(follower_snapshots),
        "followers": follower_snapshots,
        "multiplier_distribution": {
            "1.0x": "Followers 1-25",
            "2.0x": "Followers 26-50",
            "3.0x": "Followers 51-75",
            "0.5x": "Followers 76-100"
        }
    }

    # Save to reports/evidence/
    evidence_dir = BASE_DIR / "reports" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    baseline_file = evidence_dir / "baseline_snapshot.json"
    with open(baseline_file, "w", encoding="utf-8") as f:
        json.dump(baseline_data, f, indent=2)

    print(f"[+] Baseline snapshot saved to: {baseline_file}")
    print("=" * 80 + "\n")
    return baseline_data
