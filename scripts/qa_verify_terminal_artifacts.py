"""Verify delivered terminal QA artifacts without printing discovered secrets."""
import gzip
import os
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "TERMINAL_MAM_FULL_TEST_REPORT.md"
RUN = ROOT / "reports" / "terminal_mam_retest_20261121"

paths = [
    REPORT,
    ROOT / "scripts" / "qa_terminal_mam_full.py",
    ROOT / "scripts" / "qa_finalize_terminal_report.py",
    *RUN.glob("*"),
]
secret_paths = {REPORT, *RUN.glob("*")}
password = os.environ.get("TERMINAL_MAM_PASSWORD", "").encode()
patterns = [
    re.compile(rb"bt_[A-Za-z0-9._-]{20,}"),
    re.compile(rb"Bearer\s+[A-Za-z0-9._-]{20,}", re.I),
    re.compile(rb"(?:brokerToken|userToken)=(?!%?5BREDAC|\[REDAC)[^&\s]+", re.I),
]
password_hits = []
secret_hits = []
parameter_name_files = []

for path in paths:
    if not path.is_file():
        continue
    try:
        data = gzip.open(path, "rb").read() if path.suffix == ".gz" else path.read_bytes()
    except OSError:
        continue
    if password and password in data:
        password_hits.append(str(path.relative_to(ROOT)))
    if path in secret_paths and any(pattern.search(data) for pattern in patterns):
        secret_hits.append(str(path.relative_to(ROOT)))
    if b"brokerToken=" in data or b"userToken=" in data:
        parameter_name_files.append(str(path.relative_to(ROOT)))

report = REPORT.read_text(encoding="utf-8")
checks = {
    "report_total_64": "Total executed checks: **64**" in report,
    "report_pass_rows_58": report.count("| PASS |") == 58,
    "report_fail_rows_6": report.count("| FAIL |") == 6,
    "report_blocked_rows_0": report.count("| BLOCKED |") == 0,
    "report_unique_defects_5": "Unique confirmed defects: **5**" in report,
    "report_no_mojibake": "â€”" not in report,
    "no_password_in_artifacts": not password_hits,
    "no_raw_secret_pattern_in_artifacts": not secret_hits,
}
print({
    "checks": checks,
    "password_hit_files": password_hits,
    "raw_secret_pattern_files": secret_hits,
    "query_parameter_name_files": parameter_name_files,
})
if not all(checks.values()):
    raise SystemExit(1)
