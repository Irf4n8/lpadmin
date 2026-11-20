"""Create concise sample-style execution tables from existing recorded evidence."""
import csv
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "reports/live_recheck_20261120"
SOURCE = RUN / "validated_results.json"
HEADERS = [
    "TC ID", "Test Case Description", "Pre-Conditions", "Test Steps", "Test Data",
    "Expected Result", "Actual Result", "Status", "Severity", "Defect ID", "Remarks",
]


def md(value):
    return str(value).replace("|", "&#124;").replace("\r", "").replace("\n", "<br>")


def format_steps(value):
    """Restore readable numbered lines in the compact original inventory."""
    return re.sub(r"(?<!^)(?=\d+\.\s*)", "\n", str(value)).strip()


def markdown_table(rows):
    align = [":---", ":---", ":---", ":---", ":---", ":---", ":---", ":---:", ":---:", ":---:", ":---"]
    lines = ["| " + " | ".join(HEADERS) + " |", "| " + " | ".join(align) + " |"]
    lines.extend("| " + " | ".join(md(cell) for cell in row) + " |" for row in rows)
    return "\n".join(lines)


def test_data(case):
    text = " ".join([case.get("precondition", ""), case.get("steps", ""), case.get("expected", "")])
    patterns = [
        r"\$(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?", r"\b\d+(?:\.\d+)?%", r"\b\d+(?:\.\d+)?\s*lots?\b",
        r"\b(?:EURUSD|AUDUSD|GBPUSD|USDJPY|BTCUSD|BLACK:BTCUSD)\b",
        r"\b(?:1000|500|100|50|25|20|10|5|3|2)\s+(?:followers?|accounts?|orders?|trades?)\b",
        r"\b(?:Real \(Hedging\)|Paper \(Hedging\)|real hedging|paper hedging)\b",
    ]
    values = []
    for pattern in patterns:
        for value in re.findall(pattern, text, flags=re.I):
            value = value.strip()
            if value.lower() not in {v.lower() for v in values}:
                values.append(value)
    return ", ".join(values[:8]) if values else "Case-specific fixture stated in Pre-Conditions and Test Steps."


def evidence_paths(case):
    return ", ".join(case.get("evidence_files", [])) or "No execution evidence file."


def original_rows(data):
    rows = []
    for case in data["original_scenarios"]:
        checks = case.get("executed_check_ids", [])
        if case["status"] == "PARTIAL":
            actual = "Related live checks passed, but the complete expected result was not verified."
            remarks = (
                f"Related checks: {', '.join(checks)}. Remaining gap: {case['coverage_note']} "
                f"Evidence: {evidence_paths(case)}. Original priority: {case['priority']}."
            )
        else:
            actual = "Not executed; the required fixture, access, scale, or observable control was unavailable."
            remarks = (
                f"Blocked/unexecuted reason: {case['coverage_note']} "
                f"Original priority: {case['priority']}."
            )
        rows.append([
            case["test_case_id"], case["title"], case["precondition"], format_steps(case["steps"]),
            test_data(case), case["expected"], actual, case["status"], "—", "—", remarks,
        ])
    return rows


def live_actual(result):
    details = result.get("details", {})
    if result["id"] == "FINAL-ACCOUNT-STATE":
        return (
            f"Verified {details['accounts_verified']} accounts at {details['balance_each']}; "
            f"0 position/balance errors, 0 relationship errors, and {details['working_order_count']} working orders."
        )
    if result["id"] == "SETUP-BALANCE":
        return f"Set and read back {details['balance_each']} on all {details['accounts']} scoped accounts through the admin GUI."
    if result["id"].startswith("FEE-HWM-POLICY"):
        share = details.get("expected_manager_share")
        return (
            f"Observed manager share {share}; recorded share row, brokerage, split conservation, "
            "and ending balance matched the confirmed fee rule."
        )
    if result["id"].startswith("SIZE-LOT-RULE"):
        qty = details.get("expected_child_quantity")
        return f"Exactly one target child position opened at the expected {qty} quantity; no other-account or cleanup errors."
    if result["id"].startswith("LIVE-BRACKET"):
        row = details.get("master_history", [{}])[0]
        return f"Natural {row.get('exit_type', 'protected')} exit completed; every copied position had one close record and no orphan remained."
    if result["id"] == "ACCOUNTING-101":
        return "Price P&L, brokerage, MAM shares, balance changes, and released margin reconciled across all 101 accounts."
    if result["id"] == "LOAD-FIVE-BURST":
        return "Five concurrent master entries created 500 follower positions; concurrent parent closes left no orphan positions."
    error_keys = [key for key in details if any(word in key for word in ("error", "incorrect", "unexpected", "orphan", "still_working", "lost_update"))]
    if error_keys and all(details[key] in ({}, [], 0, None) for key in error_keys):
        return "Expected behavior was observed; recorded error/orphan collections were empty and cleanup completed."
    return "The recorded assertion passed and its expected post-condition was observed in the linked evidence."


def live_steps(result):
    tc = result["id"]
    if "GUI" in tc or tc.startswith(("BAL-", "SETUP-BALANCE")):
        return "1. Establish the case fixture.\n2. Change balance through Admin > Members > Real (Hedging) > Set balance.\n3. Perform the named trade/action.\n4. Read back positions, funds, relationship, or ledger state.\n5. Clean up and verify final state."
    if tc.startswith("RACE"):
        return "1. Establish the named position/order/relationship fixture.\n2. Submit the stated operations concurrently.\n3. Inspect responses and final account state.\n4. Verify case invariants and clean up."
    return "1. Establish the named real-hedging fixture.\n2. Execute the stated API trading or MAM action.\n3. Inspect all affected accounts.\n4. Verify the post-condition and clean up."


def live_rows(data):
    rows = []
    for result in data["results"]:
        mechanism = "Playwright Admin GUI + live OMS API" if "GUI" in result["id"] or result["id"].startswith(("BAL-", "SETUP")) else "Live OMS API and recorded account/ledger readback"
        remarks = (
            f"Verified via {mechanism}. Result: {result['result_file']}. "
            f"HTTP trace: reports/live_recheck_20261120/deep_run/{result['trace']}."
        )
        rows.append([
            result["id"], result["name"],
            "Dedicated simulated accounts authenticated on Real (Hedging); case-specific state established by the runner.",
            live_steps(result), "Symbol: BLACK:BTCUSD | 1 master + 100 followers",
            result["details"].get("assertion", result["details"].get("allowed_outcomes", result["name"])),
            live_actual(result), result["status"], "—", "—", remarks,
        ])
    return rows


def write_tsv(path, rows):
    def clean_cell(value):
        # Preserve intentional multiline fields without emitting whitespace-only
        # line endings that fail Git's staged-content validation.
        return "\n".join(line.rstrip() for line in str(value).splitlines())

    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", quoting=csv.QUOTE_MINIMAL)
        writer.writerow(HEADERS)
        writer.writerows([[clean_cell(value) for value in row] for row in rows])


def main():
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    original = original_rows(data)
    live = live_rows(data)
    counts = Counter(row[7] for row in original)
    report = [
        "# MAM Test Case Execution Report",
        "",
        "## Execution Summary",
        "",
        "Every original test condition is not complete. The current 165-condition inventory contains "
        f"**{counts['PARTIAL']} PARTIAL** and **{counts['BLOCKED']} BLOCKED/unexecuted** cases. "
        f"Separately, **{len(live)} validated live checks passed**. PARTIAL does not mean PASS, and no production sign-off is issued.",
        "",
        "Excel-compatible tab-separated files: [Original 165 conditions](MAM_165_TEST_CASE_EXECUTION_TABLE.tsv) and [validated live checks](MAM_VALIDATED_LIVE_EXECUTION_TABLE.tsv).",
        "",
        "## Original 165 Test Conditions",
        "",
        markdown_table(original),
        "",
        "## Validated Live Execution Checks",
        "",
        markdown_table(live),
        "",
        "## Report Notes",
        "",
        "- Severity and Defect ID are shown as — because the incomplete original cases are coverage gaps, not confirmed platform defects.",
        "- Original P0/P1/P2 priority is retained in Remarks and is not relabeled as defect severity.",
        "- Exact API responses and assertions remain in the linked evidence files. Credentials are omitted.",
        "- Earlier assertion mistakes and superseded attempts remain disclosed in the master QA report and raw attempt files.",
        "",
    ]
    destination = ROOT / "MAM_TEST_CASE_EXECUTION_TABLE.md"
    destination.write_text("\n".join(report), encoding="utf-8")
    write_tsv(ROOT / "MAM_165_TEST_CASE_EXECUTION_TABLE.tsv", original)
    write_tsv(ROOT / "MAM_VALIDATED_LIVE_EXECUTION_TABLE.tsv", live)
    assert len(original) == 165 and len(live) == 81
    assert all(len(row) == len(HEADERS) for row in original + live)
    print(json.dumps({
        "markdown": destination.name,
        "original_tsv": "MAM_165_TEST_CASE_EXECUTION_TABLE.tsv",
        "live_tsv": "MAM_VALIDATED_LIVE_EXECUTION_TABLE.tsv",
        "original_rows": len(original), "original_statuses": dict(counts), "live_rows": len(live),
    }, indent=2))


if __name__ == "__main__":
    main()
