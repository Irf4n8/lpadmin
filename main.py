#!/usr/bin/env python3
"""
BlackTrader Unified Automation CLI
==================================
Entry point for managing accounts, funding, and copy-trading on BlackTrader.

Commands:
    # 1. List available copy-trading masters:
    python main.py list-masters

    # 2. Bulk create accounts and fund balances:
    python main.py create --start 1 --end 100
    python main.py create --headed --start 1 --end 10

    # 3. Follow a copy-trading master:
    python main.py follow --master "ctmaster" --start 1 --end 100
    python main.py follow --master "ctmaster" --instance both --multiplier 2.0
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
from scripts.playwright_follow_master import follow_master_playwright, list_masters_playwright


def main():
    parser = argparse.ArgumentParser(
        description="BlackTrader Unified Automation Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py list-masters
  python main.py create --start 1 --end 100
  python main.py follow --master "ctmaster" --start 1 --end 100
  python main.py follow --master "ctmaster" --instance both --multiplier 1.5
        """
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Command: list-masters
    sub_list = subparsers.add_parser("list-masters", help="List all registered copy masters and statistics")
    sub_list.add_argument("--url", default=BASE_URL, help="Platform URL")
    sub_list.add_argument("--prefix", default=DEFAULT_PREFIX, help="Follower prefix")
    sub_list.add_argument("--domain", default=DEFAULT_DOMAIN, help="Follower domain")
    sub_list.add_argument("--password", default=MEMBER_PASSWORD, help="Probe account password")
    sub_list.add_argument("--start", type=int, default=1, help="Probe account index")
    sub_list.add_argument("--instance", choices=["paper", "real", "both"], default="paper", help="Instance to probe")
    sub_list.add_argument("--headed", action="store_true", help="Launch visible browser")

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
    sub_follow = subparsers.add_parser("follow", help="Make follower accounts copy a target master trader")
    sub_follow.add_argument("--master", required=True, help="Target Master name or client ID ('mem_...')")
    sub_follow.add_argument("--url", default=BASE_URL, help="Platform URL")
    sub_follow.add_argument("--prefix", default=DEFAULT_PREFIX, help="Follower prefix")
    sub_follow.add_argument("--domain", default=DEFAULT_DOMAIN, help="Follower domain")
    sub_follow.add_argument("--password", default=MEMBER_PASSWORD, help="Follower password")
    sub_follow.add_argument("--start", type=int, default=1, help="Starting index")
    sub_follow.add_argument("--end", type=int, default=100, help="Ending index")
    sub_follow.add_argument("--instance", choices=["paper", "real", "both"], default="paper", help="Trading instance")
    sub_follow.add_argument("--method", choices=["multiplier", "balance", "equity"], default="multiplier", help="Sizing method")
    sub_follow.add_argument("--multiplier", type=float, default=1.0, help="Lot size multiplier")
    sub_follow.add_argument("--reverse", action="store_true", help="Reverse trades (Buy -> Sell)")
    sub_follow.add_argument("--copy-mode", choices=["public", "private"], default="public", help="Copy mode")
    sub_follow.add_argument("--headed", action="store_true", help="Launch visible browser")
    sub_follow.add_argument("--slow-mo", type=int, default=0, help="Slow down actions by N ms")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "list-masters":
        list_masters_playwright(args)
    elif args.command == "create":
        create_accounts(args)
    elif args.command == "follow":
        args.list_masters = False
        follow_master_playwright(args)


if __name__ == "__main__":
    main()

