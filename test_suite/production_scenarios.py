"""Run the production scenario checklist and audit copied entries by master ID."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def scenarios():
    document = ROOT / "docs/PRODUCTION_COPY_TRADING_SCENARIOS.md"
    return {int(number): (title, detail) for number, title, detail in re.findall(
        r"^(\d+)\. \*\*(.+?)\*\* (.+)$", document.read_text(), re.MULTILINE)}


def audit(rows, ids):
    copies = Counter(str(row.get("copy_ref") or "").lstrip("-") for row in rows
                     if row.get("copy_kind") == "copy" and row.get("state") == "FILLED"
                     and row.get("order_id") and row.get("order_id") == row.get("market_order_id"))
    return {key: copies[key] for key in ids}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    modes.add_parser("list")
    guided = modes.add_parser("guided", help="Record operator observations for selected scenarios")
    guided.add_argument("ids", nargs="+", type=int)
    guided.add_argument("--output", type=Path, required=True)
    verify = modes.add_parser("audit", help="Read live order history for eligible followers")
    verify.add_argument("--master-order", action="append", required=True)
    verify.add_argument("--follower", action="append", required=True)
    verify.add_argument("--instance", choices=["real", "real-net"], required=True)
    args = parser.parse_args()
    cases = scenarios()
    if args.mode == "list":
        for number, (title, _) in cases.items():
            print(number, title)
        return 0
    if args.mode == "guided":
        if any(number not in cases for number in args.ids):
            parser.error("Unknown scenario ID")
        with args.output.open("x") as report:
            for number in args.ids:
                print(number, *cases[number], sep="\n")
                verdict = input("Observed result [pass/fail/inconclusive]: ").strip().lower()
                while verdict not in {"pass", "fail", "inconclusive"}:
                    verdict = input("Enter pass, fail or inconclusive: ").strip().lower()
                evidence = input("Evidence file or observation: ").strip()
                while not evidence:
                    evidence = input("Enter evidence file or observation: ").strip()
                print(json.dumps(dict(scenario=number, operator_verdict=verdict, evidence=evidence)),
                      file=report, flush=True)
        return 0
    from config.settings import BASE_URL, MASTER_EMAIL
    from test_suite.client import BlackTraderClient
    client = BlackTraderClient(BASE_URL)

    def orders(account):
        response = client.get_orders(account, args.instance)
        if response.get("error") or not isinstance(response.get("orders"), list):
            raise RuntimeError("Order history unavailable for " + account)
        return response["orders"]

    filled = {row["order_id"] for row in orders(MASTER_EMAIL) if row.get("state") == "FILLED"}
    if set(args.master_order) - filled:
        parser.error("One or more supplied IDs are absent from the master's filled orders")
    passed = True
    for follower in args.follower:
        counts = audit(orders(follower), args.master_order)
        print(json.dumps(dict(follower=follower, filled_copy_count=counts)))
        passed = passed and all(count == 1 for count in counts.values())
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
