"""Append validated browser cases to the terminal MAM execution report."""
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "reports" / "terminal_mam_retest_20261121"
REPORT = ROOT / "TERMINAL_MAM_FULL_TEST_REPORT.md"

fresh = json.loads((RUN / "browser_fresh_session_inspection.json").read_text(encoding="utf-8"))
login = json.loads((RUN / "browser_master_ui_login.json").read_text(encoding="utf-8"))
dashboard = json.loads((RUN / "browser_master_dashboard_dom.json").read_text(encoding="utf-8"))
frames = json.loads((RUN / "browser_master_frames.json").read_text(encoding="utf-8"))

frame = next(row for row in frames["frames"] if "chartv2.blacktrader.com" in row.get("url", ""))
assert "[REDACTED]" in frame["url"]
assert "brokerToken=" in frame["url"] and "userToken=" in frame["url"]
assert fresh["anonymous_fetch"]["account"]["status"] == 401
assert fresh["anonymous_fetch"]["positions"]["status"] == 401
assert fresh["anonymous_fetch"]["mam/follows"]["status"] == 401
assert any(row["status"] == 200 and "/real/mam/follows" in row["url"] for row in dashboard["oms_responses"])
assert any(row["status"] == 200 and "/paper/account" in row["url"] for row in dashboard["oms_responses"])

cases = [
    {
        "id": "TERM-UI-PASSWORD-001",
        "description": "Password field masks entered credentials",
        "expected": "The password control uses a masked password input.",
        "actual": "The terminal login form rendered the password control as input type `password`; the screenshot shows masked characters.",
        "status": "PASS", "severity": "—", "defect": "—",
        "evidence": "terminal_master_ui_login_failure.png",
    },
    {
        "id": "TERM-UI-LOGIN-001",
        "description": "Valid master login opens the trading dashboard",
        "expected": "Valid master credentials open the dashboard and authorized MAM reads succeed.",
        "actual": "The browser reached `/test/home/dashboard`; the protected Real MAM relationship request returned HTTP 200 and the dashboard rendered.",
        "status": "PASS", "severity": "—", "defect": "—",
        "evidence": "terminal_master_dashboard_instance_mismatch.png",
    },
    {
        "id": "TERM-UI-AUTHZ-001",
        "description": "Fresh unauthenticated browser cannot read account or MAM data",
        "expected": "Protected account, positions and MAM relationship endpoints return 401 without a token.",
        "actual": "With no local/session storage and no authorization header, account, positions and MAM relationship reads each returned HTTP 401.",
        "status": "PASS", "severity": "—", "defect": "—",
        "evidence": "browser_fresh_session_inspection.json",
    },
    {
        "id": "TERM-UI-INSTANCE-001",
        "description": "MAM widget and trading panel use the same Real Hedging instance",
        "expected": "A MAM master dashboard must bind both MAM controls and order-entry/trade panels to Real Hedging.",
        "actual": "After master login, the trading panel displayed Paper Hedging and called `/paper/account`, `/paper/orders` and `/paper/history`, while the MAM widget simultaneously called `/real/mam/masters`, `/real/mam/follows` and `/real/mam/shares`.",
        "status": "FAIL", "severity": "High", "defect": "TERM-UI-001",
        "evidence": "browser_master_dashboard_dom.json; terminal_master_dashboard_instance_mismatch.png",
    },
    {
        "id": "TERM-UI-TOKEN-001",
        "description": "Trading credentials are not placed in iframe URL query parameters",
        "expected": "Session and broker credentials use protected headers or an equivalent mechanism and do not appear in URLs.",
        "actual": "The cross-origin chart iframe URL contained both `brokerToken` and `userToken` query parameters. Values were redacted from evidence and the broker token was revoked successfully through logout (HTTP 204).",
        "status": "FAIL", "severity": "High", "defect": "TERM-SEC-001",
        "evidence": "browser_master_frames.json (redacted)",
    },
]

(RUN / "ui_validated_results.json").write_text(json.dumps({
    "generated_at": "2026-11-21",
    "cases": cases,
    "credentials_in_evidence": False,
    "revocation_http": 204,
}, indent=2), encoding="utf-8")


def esc(value):
    return str(value).replace("|", "\\|").replace("\n", "<br>")


headers = [
    "TC ID", "Test Case Description", "Pre-Conditions", "Test Steps", "Test Data",
    "Expected Result", "Actual Result", "Status", "Severity", "Defect ID", "Remarks",
]
table = [
    "| " + " | ".join(headers) + " |",
    "| " + " | ".join([":---"] * 7 + [":---:"] * 3 + [":---"]) + " |",
]
for case in cases:
    row = [
        case["id"], case["description"],
        "Fresh Chromium context; terminal master test credentials for valid-login checks; no stored session for authorization checks.",
        "1. Open the terminal in a fresh browser.<br>2. Inspect the login control or authenticate as the master.<br>3. Record instance-specific network calls and protected-resource responses.<br>4. Save a redacted screenshot/JSON observation.",
        "https://terminal.blacktrader.com/test; mamhm@mailinator.com; browser storage/cookie inspection without recording values.",
        case["expected"], case["actual"], case["status"], case["severity"], case["defect"],
        "Evidence: reports/terminal_mam_retest_20261121/" + case["evidence"],
    ]
    table.append("| " + " | ".join(esc(value) for value in row) + " |")

ui_section = "\n".join([
    "## Browser UI Execution Table",
    "",
    *table,
    "",
])

text = REPORT.read_text(encoding="utf-8")
text = text.replace("- Total executed checks: **59**", "- Total executed checks: **64**")
text = text.replace("- PASS: **55**", "- PASS: **58**")
text = text.replace("- FAIL: **4**", "- FAIL: **6**")
text = text.replace(
    "- BLOCKED: **0**",
    "- BLOCKED: **0**\n- Unique confirmed defects: **5** — 2 Critical and 3 High.",
)
needle = "- **TERM-WEB-001 — High:** The HTTPS terminal entry route redirected to an HTTP URL."
text = text.replace(
    needle,
    needle
    + "\n- **TERM-UI-001 — High:** The MAM widget used Real while the trading panel defaulted to Paper, allowing a manager to place a non-copying paper trade from the same dashboard."
    + "\n- **TERM-SEC-001 — High:** Broker and user tokens were placed in a cross-origin iframe URL query string, exposing credentials to URL/history/proxy logging. The observed broker token was revoked after capture.",
)
text = text.replace("## Coverage Limitations", ui_section + "\n## Coverage Limitations")
text = text.replace(
    "- Final snapshot: `reports/terminal_mam_retest_20261121/final_state.json`",
    "- Final snapshot: `reports/terminal_mam_retest_20261121/final_state.json`\n"
    "- Browser cases: `reports/terminal_mam_retest_20261121/ui_validated_results.json`\n"
    "- Redacted dashboard network evidence: `reports/terminal_mam_retest_20261121/browser_master_dashboard_dom.json`\n"
    "- UI screenshots: `reports/terminal_mam_retest_20261121/terminal_master_dashboard_instance_mismatch.png` and `terminal_master_ui_login_failure.png`",
)
REPORT.write_text(text, encoding="utf-8")

print(json.dumps({
    "report": str(REPORT),
    "total": 64,
    "pass": 58,
    "fail": 6,
    "blocked": 0,
    "unique_defects": 5,
    "ui_cases": len(cases),
}, indent=2))
