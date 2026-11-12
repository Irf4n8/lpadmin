#!/usr/bin/env python3
"""
BlackTrader Unified Automation CLI (MAM Dedicated)
===================================================
Entry point for managing accounts, funding, and MAM on BlackTrader.

Commands:
    # 1. List available MAM masters:
    python main.py list-masters

    # 2. Bulk create accounts and fund balances:
    python main.py create --start 1 --end 100 --prefix mamfollower
    python main.py create --headed --start 1 --end 10

    # 3. Follow a MAM master:
    python main.py follow --master "mammaster" --start 1 --end 100 --multiplier 2.0
    python main.py follow --master "mammaster" --method balance --start 1 --end 100
"""

import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
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
from scripts.playwright_create_accounts import create_accounts
from follow_mam import list_mam_masters, resolve_mam_master_id, MamFollowerClient


def main():
    parser = argparse.ArgumentParser(
        description="BlackTrader Unified Automation Tool (MAM Dedicated)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py list-masters
  python main.py create --start 1 --end 100 --prefix mamfollower
  python main.py follow --master "mammaster" --start 1 --end 100
  python main.py follow --master "mammaster" --method balance --start 1 --end 100
        """
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Command: list-masters
    sub_list = subparsers.add_parser("list-masters", help="List all registered MAM masters and statistics")
    sub_list.add_argument("--url", default=BASE_URL, help="Platform URL")
    sub_list.add_argument("--prefix", default=DEFAULT_PREFIX, help="Follower prefix")
    sub_list.add_argument("--domain", default=DEFAULT_DOMAIN, help="Follower domain")
    sub_list.add_argument("--password", default=MEMBER_PASSWORD, help="Probe account password")
    sub_list.add_argument("--start", type=int, default=1, help="Probe account index")
    sub_list.add_argument("--instance", choices=["paper", "real", "both"], default="paper", help="Instance to probe")

    # Command: create
    sub_create = subparsers.add_parser("create", help="Bulk create trader accounts and fund balances")
    sub_create.add_argument("--url", default=BASE_URL, help="Admin URL")
    sub_create.add_argument("--admin-email", default=ADMIN_EMAIL, help="Admin email")
    sub_create.add_argument("--admin-pass", default=ADMIN_PASSWORD, help="Admin password")
    sub_create.add_argument("--prefix", default=DEFAULT_PREFIX, help="Email prefix")
    sub_create.add_argument("--domain", default=DEFAULT_DOMAIN, help="Email domain")
    sub_create.add_argument("--member-pass", default=MEMBER_PASSWORD, help="Member password")
    sub_create.add_argument("--start", type=int, default=1, help="Starting index")
    sub_create.add_argument("--end", type=int, default=100, help="Ending index")
    sub_create.add_argument("--balance", type=float, default=DEFAULT_BALANCE, help="Balance amount (10cr = 100000000)")
    sub_create.add_argument("--instances", default=DEFAULT_INSTANCES, help="Instances to fund (paper,real)")
    sub_create.add_argument("--headed", action="store_true", help="Launch visible browser")
    sub_create.add_argument("--slow-mo", type=int, default=0, help="Slow down actions by N ms")

    # Command: follow
    sub_follow = subparsers.add_parser("follow", help="Make follower accounts join a target MAM manager")
    sub_follow.add_argument("--master", default="mammaster", help="Target MAM Master name or client ID ('mem_...')")
    sub_follow.add_argument("--url", default=BASE_URL, help="Platform URL")
    sub_follow.add_argument("--prefix", default=DEFAULT_PREFIX, help="Follower prefix")
    sub_follow.add_argument("--domain", default=DEFAULT_DOMAIN, help="Follower domain")
    sub_follow.add_argument("--password", default=MEMBER_PASSWORD, help="Follower password")
    sub_follow.add_argument("--start", type=int, default=1, help="Starting index")
    sub_follow.add_argument("--end", type=int, default=100, help="Ending index")
    sub_follow.add_argument("--instance", choices=["paper", "real", "both"], default="paper", help="Trading instance")
    sub_follow.add_argument("--method", choices=["multiplier", "balance", "equity"], default="multiplier", help="Sizing method")
    sub_follow.add_argument("--multiplier", type=float, default=2.0, help="Lot size multiplier")
    sub_follow.add_argument("--reverse", action="store_true", help="Reverse trades (Buy -> Sell)")
    sub_follow.add_argument("--copy-mode", choices=["public", "private"], default="public", help="Copy mode")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "list-masters":
        probe_email = f"{args.prefix}{args.start}@{args.domain}"
        inst = "paper" if args.instance == "both" else args.instance
        list_mam_masters(args.url, probe_email, args.password, inst)
    elif args.command == "create":
        create_accounts(args)
    elif args.command == "follow":
        probe_email = f"{args.prefix}{args.start}@{args.domain}"
        client = MamFollowerClient(args.url)
        if not client.login(probe_email, args.password):
            print(f"[-] Login failed for probe account {probe_email}")
            sys.exit(1)
        client.get_chart_token()
        inst_for_lookup = "paper" if args.instance == "both" else args.instance
        master_id = resolve_mam_master_id(client, args.master, inst_for_lookup)
        if not master_id:
            print(f"[-] Could not find MAM master matching '{args.master}'")
            sys.exit(1)

        target_instances = ["paper", "real"] if args.instance == "both" else [args.instance]
        for i in range(args.start, args.end + 1):
            email = f"{args.prefix}{i}@{args.domain}"
            f_client = MamFollowerClient(args.url)
            if not f_client.login(email, args.password):
                print(f"[{i}] [-] Login failed for {email}")
                continue
            f_client.get_chart_token()
            for inst in target_instances:
                ok, msg = f_client.follow_master(
                    master_client_id=master_id,
                    instance=inst,
                    method=args.method,
                    multiplier=args.multiplier,
                    reverse=args.reverse,
                    copy_mode=args.copy_mode
                )
                print(f"[{i}] [{'+' if ok else '-'}] {email} ({inst}) -> {msg}")


if __name__ == "__main__":
    main()

