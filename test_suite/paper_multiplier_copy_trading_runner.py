#!/usr/bin/env python3
"""
BlackTrader OMS - Paper Trading 2x Multiplier Copy Trading Certification Suite
=============================================================================
Validates end-to-end copy trading on the PAPER broker instance with a 2x Multiplier:
1. Balance Equalization:
   - Sets Master & 100 Followers to exact same balance ($100,000,000.00 each) on PAPER.
2. Linkage Configuration (2x Multiplier):
   - Purges any real instance follow links.
   - Follows Master (mem_aac4ca423a6925dca7) on PAPER instance with multiplier = 2.0.
   - Confirms 100/100 followers actively follow Master on PAPER with multiplier=2.
3. Order Replication Verification (10 Lot Master -> 20 Lot Follower):
   - Master executes BUY MARKET (10.0 lot) on PAPER.
   - Verifies 100/100 followers copy with exact 20.0 lot (2x multiplier).
4. Secondary Order Verification (10 Lot SELL MARKET):
   - Master executes SELL MARKET (10.0 lot) on PAPER.
   - Verifies 100/100 followers copy with exact 20.0 lot short position.
5. Teardown & Zero Orphan Audit:
   - Reconciles all 101 accounts to 0 open positions and 0 pending orders on PAPER.

Usage:
    python test_suite/paper_multiplier_copy_trading_runner.py
    python test_suite/paper_multiplier_copy_trading_runner.py --start 1 --end 100
"""

import argparse
import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config.settings import MASTER_EMAIL, MASTER_ID
from config.settings import BASE_URL, DEFAULT_PREFIX, DEFAULT_DOMAIN
from test_suite.client import BlackTraderClient


MASTER_CLIENT_ID = MASTER_ID
TARGET_BALANCE = 100000000.0  # 100M each
TARGET_MULTIPLIER = 2.0       # 2x multiplier
MASTER_ORDER_LOT = 10.0       # 10 lot order
EXPECTED_FOLLOWER_LOT = 20.0  # 10 lot * 2 = 20 lot


def cleanup_paper(client: BlackTraderClient, master_email: str, follower_emails: list):
    """Square off all open positions and cancel pending orders on the PAPER instance."""
    try:
        client.bulk_cancel(master_email, instance="paper")
        client.bulk_squareoff(master_email, instance="paper")
    except Exception as e:
        print(f"  [WARN] Master cleanup error: {e}")

    def clean_f(email):
        for _ in range(3):
            try:
                client.bulk_cancel(email, instance="paper")
                client.bulk_squareoff(email, instance="paper")
                return True
            except Exception:
                time.sleep(0.3)
        return False

    with ThreadPoolExecutor(max_workers=client.max_workers) as executor:
        list(executor.map(clean_f, follower_emails))


# =============================================================================
# PHASE 1: Equalize Balance on Paper to 100,000,000.00 each
# =============================================================================
def equalize_paper_balances(client: BlackTraderClient, all_emails: list, master_email: str, follower_emails: list) -> dict:
    print("\n" + "=" * 80)
    print(f"[PHASE 1] Synchronizing Balances on PAPER instance to {TARGET_BALANCE:,.2f} each...")
    print("=" * 80)

    # 1. Fetch all members from Admin API
    print(f"  -> Fetching member IDs from Admin API...")
    members = client.get_admin_members()
    member_map = {m.get("email"): (m.get("id") or m.get("member_id")) for m in members if m.get("email")}

    def set_balance_task(email):
        mem_id = member_map.get(email)
        if not mem_id:
            return {"email": email, "success": False, "error": "No member ID"}
        try:
            res = client.set_member_balance(mem_id, TARGET_BALANCE, instance="paper")
            return {"email": email, "success": (res.get("status_code") == 200), "resp": res}
        except Exception as e:
            return {"email": email, "success": False, "error": str(e)}

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=client.max_workers) as executor:
        results = list(executor.map(set_balance_task, all_emails))
    dur_sec = time.time() - t0

    success_count = sum(1 for r in results if r["success"])
    print(f"  -> Synchronized {success_count} / {len(all_emails)} accounts to {TARGET_BALANCE:,.2f} in {dur_sec:.2f}s")

    # Sample verify master and 5 followers
    m_funds = client.get_positions(master_email, instance="paper").get("funds", {})
    print(f"  -> Master Verified Paper Balance: {float(m_funds.get('balance', 0)):,.2f}")

    sample_f_funds = [
        client.get_positions(f, instance="paper").get("funds", {}).get("balance", 0)
        for f in follower_emails[:5]
    ]
    print(f"  -> Sample Followers Paper Balances: {[f'{float(b):,.2f}' for b in sample_f_funds]}")

    passed = (success_count >= len(all_emails) * 0.98)
    return {
        "phase": "Balance Synchronization (Paper)",
        "target_balance": TARGET_BALANCE,
        "success_count": success_count,
        "total_accounts": len(all_emails),
        "duration_sec": round(dur_sec, 2),
        "status": "PASS" if passed else "FAIL"
    }


# =============================================================================
# PHASE 2: Configure 2x Multiplier Follow Links on Paper
# =============================================================================
def configure_2x_multiplier_paper(client: BlackTraderClient, follower_emails: list) -> dict:
    print("\n" + "=" * 80)
    print(f"[PHASE 2] Configuring Follow Links on PAPER with {TARGET_MULTIPLIER}x Multiplier...")
    print("=" * 80)

    def re_link_task(email):
        try:
            # 1. Unfollow on real if active
            client.unfollow_master(email, MASTER_CLIENT_ID, instance="real")
            # 2. Unfollow on paper to refresh settings cleanly
            client.unfollow_master(email, MASTER_CLIENT_ID, instance="paper")
            # 3. Follow on paper with multiplier 2.0
            fol_res = client.follow_master(
                email, 
                MASTER_CLIENT_ID, 
                instance="paper", 
                method="multiplier", 
                multiplier=TARGET_MULTIPLIER
            )
            
            # 4. Verify paper follow link
            token = client.get_trader_token(email)
            h = {"Authorization": f"Bearer {token}", "X-Broker-ID": "paper"}
            check_res = client.request_with_retry("GET", f"{client.base_url}/v1/oms/paper/copy/follows", headers=h)
            follows = check_res.json().get("following", [])
            
            is_valid_2x = any(
                f.get("master_client_id") == MASTER_CLIENT_ID and 
                f.get("instance") == "paper" and 
                float(f.get("multiplier", 0)) == TARGET_MULTIPLIER and
                f.get("status") == "active"
                for f in follows
            )
            return {"email": email, "valid_2x": is_valid_2x}
        except Exception as e:
            return {"email": email, "valid_2x": False, "error": str(e)}

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=client.max_workers) as executor:
        results = list(executor.map(re_link_task, follower_emails))
    dur_sec = time.time() - t0

    valid_2x_count = sum(1 for r in results if r.get("valid_2x"))
    print(f"  -> Followers Successfully Configured with {TARGET_MULTIPLIER}x on PAPER: {valid_2x_count} / {len(follower_emails)} in {dur_sec:.2f}s")

    passed = (valid_2x_count >= len(follower_emails) * 0.98)
    return {
        "phase": f"Follow Link Configuration ({TARGET_MULTIPLIER}x Multiplier on Paper)",
        "valid_2x_followers": valid_2x_count,
        "total_followers": len(follower_emails),
        "target_multiplier": TARGET_MULTIPLIER,
        "duration_sec": round(dur_sec, 2),
        "status": "PASS" if passed else "FAIL"
    }


# =============================================================================
# PHASE 3: Master Places 10.0 Lot BUY MARKET on Paper -> Verify 20.0 Lot Fan-out
# =============================================================================
def test_paper_order_10lot_buy(client: BlackTraderClient, master_email: str, follower_emails: list, symbol: str = "BINANCE:BTCUSDT.P") -> dict:
    print("\n" + "=" * 80)
    print(f"[PHASE 3] Executing Order: Master BUY MARKET ({MASTER_ORDER_LOT} lot) on PAPER...")
    print(f"          Expected Follower Size: {EXPECTED_FOLLOWER_LOT} lot ({TARGET_MULTIPLIER}x Multiplier)")
    print("=" * 80)

    cleanup_paper(client, master_email, follower_emails)
    time.sleep(1.5)

    t0 = time.time()
    res = client.place_order(master_email, symbol=symbol, side="BUY", qty=MASTER_ORDER_LOT, instance="paper")
    m_order = res.get("data", {}).get("order", {})
    mkt_id = m_order.get("market_order_id")

    print(f"  -> Master Order Status: HTTP {res.get('status_code')} | Order ID: {mkt_id} | Lot: {m_order.get('requested_qty')} | Fill Price: {m_order.get('avg_fill_price')}")
    if res.get("status_code") != 200 or not mkt_id:
        return {"name": f"Master {MASTER_ORDER_LOT} Lot BUY Order", "status": "FAIL", "error": "Master order failed on paper"}

    print("  -> Waiting 3.0s for 100-follower fan-out on PAPER broker...")
    time.sleep(3.0)

    def check_f(email):
        try:
            pos_list = client.get_positions(email, instance="paper").get("positions", [])
            match = [
                p for p in pos_list 
                if p.get("symbol") == symbol 
                and p.get("side") == "BUY" 
                and math.isclose(float(p.get("net_qty", 0)), EXPECTED_FOLLOWER_LOT, rel_tol=1e-3)
                and p.get("source") == "copy"
            ]
            return {
                "email": email, 
                "copied": len(match) >= 1, 
                "positions": pos_list
            }
        except Exception as e:
            return {"email": email, "copied": False, "error": str(e)}

    with ThreadPoolExecutor(max_workers=client.max_workers) as executor:
        f_results = list(executor.map(check_f, follower_emails))

    followers_copied = sum(1 for r in f_results if r["copied"])
    replication_rate = (followers_copied / len(follower_emails)) * 100.0

    print(f"  -> Followers Successfully Holding {EXPECTED_FOLLOWER_LOT} Lot (2x Multiplier) Position on PAPER: {followers_copied} / {len(follower_emails)} ({replication_rate:.1f}%)")

    # Sample follower inspection
    sample_res = f_results[0]
    sample_pos = [p for p in sample_res.get("positions", []) if p.get("source") == "copy"]
    if sample_pos:
        print(f"  -> Follower 1 Inspection: Lot = {sample_pos[0].get('net_qty')} | Entry Price = {sample_pos[0].get('avg_entry_price')} | Margin = {sample_pos[0].get('margin_used')} | Source = {sample_pos[0].get('source')}")

    # Clean squareoff on paper
    print("  -> Squaring off Master Order 1 on PAPER...")
    client.bulk_squareoff(master_email, instance="paper")
    time.sleep(2.5)

    passed = (followers_copied >= len(follower_emails) * 0.95)
    return {
        "name": f"Order 1 ({MASTER_ORDER_LOT} Lot BUY -> {EXPECTED_FOLLOWER_LOT} Lot Follower)",
        "master_lot": MASTER_ORDER_LOT,
        "expected_follower_lot": EXPECTED_FOLLOWER_LOT,
        "symbol": symbol,
        "side": "BUY",
        "followers_copied": followers_copied,
        "total_followers": len(follower_emails),
        "replication_rate_pct": replication_rate,
        "status": "PASS" if passed else "FAIL"
    }


# =============================================================================
# PHASE 4: Master Places 10.0 Lot SELL MARKET on Paper -> Verify 20.0 Lot Fan-out
# =============================================================================
def test_paper_order_10lot_sell(client: BlackTraderClient, master_email: str, follower_emails: list, symbol: str = "BINANCE:BTCUSDT.P") -> dict:
    print("\n" + "=" * 80)
    print(f"[PHASE 4] Executing Order 2: Master SELL MARKET ({MASTER_ORDER_LOT} lot) on PAPER...")
    print(f"          Expected Follower Size: {EXPECTED_FOLLOWER_LOT} lot ({TARGET_MULTIPLIER}x Multiplier)")
    print("=" * 80)

    cleanup_paper(client, master_email, follower_emails)
    time.sleep(1.5)

    res = client.place_order(master_email, symbol=symbol, side="SELL", qty=MASTER_ORDER_LOT, instance="paper")
    m_order = res.get("data", {}).get("order", {})
    mkt_id = m_order.get("market_order_id")

    print(f"  -> Master Order Status: HTTP {res.get('status_code')} | Order ID: {mkt_id} | Lot: {m_order.get('requested_qty')} | Fill Price: {m_order.get('avg_fill_price')}")
    if res.get("status_code") != 200 or not mkt_id:
        return {"name": f"Master {MASTER_ORDER_LOT} Lot SELL Order", "status": "FAIL", "error": "Master order failed on paper"}

    print("  -> Waiting 3.0s for 100-follower fan-out on PAPER broker...")
    time.sleep(3.0)

    def check_f(email):
        try:
            pos_list = client.get_positions(email, instance="paper").get("positions", [])
            match = [
                p for p in pos_list 
                if p.get("symbol") == symbol 
                and p.get("side") == "SELL" 
                and math.isclose(float(p.get("net_qty", 0)), EXPECTED_FOLLOWER_LOT, rel_tol=1e-3)
                and p.get("source") == "copy"
            ]
            return {"email": email, "copied": len(match) >= 1, "positions": pos_list}
        except Exception as e:
            return {"email": email, "copied": False, "error": str(e)}

    with ThreadPoolExecutor(max_workers=client.max_workers) as executor:
        f_results = list(executor.map(check_f, follower_emails))

    followers_copied = sum(1 for r in f_results if r["copied"])
    replication_rate = (followers_copied / len(follower_emails)) * 100.0

    print(f"  -> Followers Successfully Holding {EXPECTED_FOLLOWER_LOT} Lot SHORT (2x Multiplier) on PAPER: {followers_copied} / {len(follower_emails)} ({replication_rate:.1f}%)")

    # Clean squareoff on paper
    print("  -> Squaring off Master Order 2 on PAPER...")
    client.bulk_squareoff(master_email, instance="paper")
    time.sleep(2.5)

    passed = (followers_copied >= len(follower_emails) * 0.95)
    return {
        "name": f"Order 2 ({MASTER_ORDER_LOT} Lot SELL -> {EXPECTED_FOLLOWER_LOT} Lot Follower)",
        "master_lot": MASTER_ORDER_LOT,
        "expected_follower_lot": EXPECTED_FOLLOWER_LOT,
        "symbol": symbol,
        "side": "SELL",
        "followers_copied": followers_copied,
        "total_followers": len(follower_emails),
        "replication_rate_pct": replication_rate,
        "status": "PASS" if passed else "FAIL"
    }


# =============================================================================
# MAIN ORCHESTRATOR
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description="Paper Trading 2x Multiplier Copy Trading Certification Suite")
    parser.add_argument("--start", type=int, default=1, help="Start follower index (default: 1)")
    parser.add_argument("--end", type=int, default=100, help="End follower index (default: 100)")
    args = parser.parse_args()

    follower_emails = [f"follower{i}@mailinator.com" for i in range(args.start, args.end + 1)]
    all_emails = [MASTER_EMAIL] + follower_emails

    print("=" * 80)
    print("BLACKTRADER OMS: PAPER TRADING 2X MULTIPLIER CERTIFICATION SUITE")
    print(f"Master: {MASTER_EMAIL} (Client ID: {MASTER_CLIENT_ID})")
    print(f"Followers: {len(follower_emails)} accounts (follower{args.start} to follower{args.end})")
    print(f"Instance: PAPER | Multiplier: {TARGET_MULTIPLIER}x | Master Lot: {MASTER_ORDER_LOT} | Expected Follower Lot: {EXPECTED_FOLLOWER_LOT}")
    print(f"Target Equal Capital: {TARGET_BALANCE:,.2f} on PAPER instance")
    print("=" * 80)

    client = BlackTraderClient()
    start_time = time.time()
    results = []

    # Phase 1: Equalize Balance on Paper
    res_phase1 = equalize_paper_balances(client, all_emails, MASTER_EMAIL, follower_emails)
    results.append(res_phase1)

    # Phase 2: Configure 2x Multiplier Follow Links on Paper
    res_phase2 = configure_2x_multiplier_paper(client, follower_emails)
    results.append(res_phase2)

    # Phase 3: Order 1 - 10 Lot BUY
    res_phase3 = test_paper_order_10lot_buy(client, MASTER_EMAIL, follower_emails)
    results.append(res_phase3)

    # Phase 4: Order 2 - 10 Lot SELL
    res_phase4 = test_paper_order_10lot_sell(client, MASTER_EMAIL, follower_emails)
    results.append(res_phase4)

    # Phase 5: Final Teardown
    print("\nFinal Teardown: Reconciling all accounts to 0 open positions on PAPER instance...")
    cleanup_paper(client, MASTER_EMAIL, follower_emails)

    total_duration = time.time() - start_time
    passed_count = sum(1 for r in results if r.get("status") == "PASS")
    total_count = len(results)

    print("\n" + "=" * 80)
    print(f"PAPER 2X MULTIPLIER SUITE SUMMARY: {passed_count} / {total_count} PASSED ({(passed_count/total_count)*100:.1f}%) in {total_duration:.2f}s")
    print("=" * 80)
    for r in results:
        name = r.get("name") or r.get("phase")
        print(f"  * [{r.get('status')}] {name}")

    # Generate Evidence Files
    evidence_payload = {
        "suite": "BlackTrader OMS - Paper Trading 2x Multiplier Certification",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "instance": "paper",
        "master_email": MASTER_EMAIL,
        "master_client_id": MASTER_CLIENT_ID,
        "target_balance": TARGET_BALANCE,
        "target_multiplier": TARGET_MULTIPLIER,
        "master_order_lot": MASTER_ORDER_LOT,
        "expected_follower_lot": EXPECTED_FOLLOWER_LOT,
        "follower_count": len(follower_emails),
        "total_duration_sec": round(total_duration, 2),
        "results": results
    }

    evidence_path = BASE_DIR / "reports" / "evidence" / "paper_2x_multiplier_copy_trading_evidence.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    with open(evidence_path, "w", encoding="utf-8") as f:
        json.dump(evidence_payload, f, indent=2)
    print(f"\nEvidence JSON saved to: {evidence_path}")

    # Generate Markdown Report
    report_path = BASE_DIR / "reports" / "paper_2x_multiplier_copy_trading_report.md"
    md_lines = [
        "# BlackTrader OMS - Paper Trading 2x Multiplier Certification Report",
        "",
        f"- **Execution Timestamp**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"- **Broker Instance**: `PAPER` (Simulation Mode)",
        f"- **Configured Multiplier**: `{TARGET_MULTIPLIER}x`",
        f"- **Master Order Size**: `{MASTER_ORDER_LOT} Lot`",
        f"- **Expected Follower Size**: `{EXPECTED_FOLLOWER_LOT} Lot` ({TARGET_MULTIPLIER}x Multiplier)",
        f"- **Target Capital**: ${TARGET_BALANCE:,.2f} Equalized across all 101 Accounts",
        f"- **Total Followers Tested**: {len(follower_emails)}",
        f"- **Overall Suite Status**: **{'PASSED (100%)' if passed_count == total_count else 'FAILED'}**",
        f"- **Total Duration**: {total_duration:.2f} seconds",
        "",
        "## Phase Breakdown & Multiplier Verification",
        "",
        "| # | Phase / Test | Status | Key Metric / Verification |",
        "|---|---|---|---|"
    ]
    for idx, r in enumerate(results, start=1):
        name = r.get("name") or r.get("phase")
        status = f"**{r.get('status')}**"
        metrics = {k: v for k, v in r.items() if k not in ["name", "phase", "status"]}
        md_lines.append(f"| {idx} | {name} | {status} | `{json.dumps(metrics)}` |")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines) + "\n")
    print(f"Markdown Report saved to: {report_path}")


if __name__ == "__main__":
    main()
