"""
Suite registry - the single source of truth for what the dashboard can launch.

To add a new suite: write a runner in test_suite/, then add ONE entry to SUITES below.
The launcher UI, the run options and the command line are all generated from it.

Fields
------
key        unique id used by the API
name       short title shown on the button
desc       one-line explanation shown under the title
category   launcher group heading
icon       Font Awesome icon name (without the `fa-` prefix)
tone       ok | cyan | warn | danger | violet  (accent colour)
tag        small badge text
script     path relative to repo root
flags      CLI flags the runner understands: start, end, instance, lot, orders_count, burst, ramp, profile,
           only (comma list of step ids such as E05,E06 - used by "re-run this step")
risk       safe      - paper trading only, no real money
           real      - touches the REAL instance (requires typed confirmation)
           destructive - closes positions / cancels orders everywhere (requires confirmation)
fixed_instance  force a specific instance regardless of the UI selector (None = honour selector)
args       optional fixed CLI arguments always passed (lets one script back several launcher entries)
minutes    rough duration shown to the user
"""

import re
import sys
from typing import Any, Dict, List, Optional

PY = sys.executable or "python"

SUITES: List[Dict[str, Any]] = [
    # ---- Start here ------------------------------------------------------------------
    dict(key="e2e", name="End-to-End Test", desc="Full trade lifecycle: open, TP/SL, partial, hedge, close, pending, validation, accounting",
         category="Start here", icon="route", tone="ok", tag="16 steps", script="test_suite/e2e_runner.py",
         flags=["start", "end", "instance", "lot", "only"], risk="safe", minutes=4),
    dict(key="symbols_sample", name="Market Types Check", desc="One symbol of every market group: crypto, forex, metals, stocks, indices, F&O...",
         category="Start here", icon="globe", tone="cyan", tag="18 groups", script="test_suite/symbol_coverage_runner.py",
         flags=["start", "end", "instance"], args=["--sample"], risk="safe", minutes=2),
    dict(key="symbols_all", name="All Symbols", desc="Every listed symbol (~3,600): open, copy, close, PnL. Closed markets are skipped",
         category="Start here", icon="list-check", tone="violet", tag="Every symbol", script="test_suite/symbol_coverage_runner.py",
         flags=["start", "end", "instance"], risk="safe", minutes=60),

    # ---- Copy modes ------------------------------------------------------------------
    dict(key="multiplier", name="Multiplier Mode", desc="1x / 2x / 3x / 0.5x multipliers across followers",
         category="Copy modes", icon="bolt", tone="warn", tag="Varied", script="test_suite/runner.py",
         flags=["start", "end", "instance", "lot", "orders_count", "burst"], risk="safe", minutes=4),
    dict(key="balance", name="Balance-Based Mode", desc="Position sizing by balance ratio",
         category="Copy modes", icon="wallet", tone="ok", tag="Sizing", script="test_suite/balance_mode_runner.py",
         flags=["start", "end", "instance", "lot", "orders_count", "burst"], risk="safe", minutes=4),
    dict(key="equity", name="Equity-Based Mode", desc="Position sizing by equity ratio",
         category="Copy modes", icon="scale-balanced", tone="cyan", tag="Sizing", script="test_suite/equity_mode_runner.py",
         flags=["start", "end", "instance", "lot", "orders_count", "burst"], risk="safe", minutes=4),
    dict(key="symmetry", name="Buy/Sell Parity & Stop", desc="Market, limit and stop orders in both directions",
         category="Copy modes", icon="arrows-left-right", tone="cyan", tag="Parity", script="test_suite/buy_sell_symmetric_runner.py",
         flags=["start", "end", "instance", "lot", "orders_count"], risk="safe", minutes=3),
    dict(key="copy_complex", name="Complex Copy Scenarios", desc="Model-checked: mixed modes, reverse, pyramiding, TP/SL sync, random walk",
         category="Copy modes", icon="diagram-project", tone="violet", tag="10 scenarios", script="test_suite/copy_complex_runner.py",
         flags=["start", "end", "instance"], risk="safe", minutes=8),
    dict(key="paper_2x", name="Paper 2x Certification", desc="10 lot master -> 20 lot follower, end to end",
         category="Copy modes", icon="angles-up", tone="ok", tag="2x", script="test_suite/paper_multiplier_copy_trading_runner.py",
         flags=["start", "end"], risk="safe", fixed_instance="paper", minutes=3),

    # ---- Races & concurrency ---------------------------------------------------------
    dict(key="breakpoint", name="Breakpoint & Race Hunter", desc="Tries to break the OMS: double-close, torn TP/SL, load ramp, fuzz",
         category="Races & concurrency", icon="burst", tone="danger", tag="11 checks", script="test_suite/breakpoint_race_runner.py",
         flags=["start", "end", "instance", "ramp"], risk="safe", minutes=6),
    dict(key="race", name="Race Conditions", desc="Flash trades, dual orders, 10-thread storm, unfollow race",
         category="Races & concurrency", icon="flag-checkered", tone="violet", tag="Races", script="test_suite/race_conditions_runner.py",
         flags=["start", "end", "instance"], risk="safe", minutes=3),
    dict(key="extreme", name="Extreme Scenarios", desc="Rapid reversal, capital shock, straddle, micro-lots",
         category="Races & concurrency", icon="bolt-lightning", tone="danger", tag="7 scenarios", script="test_suite/extreme_scenarios_and_race_runner.py",
         flags=["start", "end", "instance"], risk="safe", minutes=5),
    dict(key="pending_trigger_race", name="Trigger vs Modify/Cancel", desc="Pending order trigger racing cancel and TP/SL edits",
         category="Races & concurrency", icon="clock-rotate-left", tone="cyan", tag="Trigger race", script="test_suite/pending_trigger_race_runner.py",
         flags=["start", "end", "instance"], risk="safe", minutes=4),

    # ---- Orders & state --------------------------------------------------------------
    dict(key="pending", name="Pending Live Triggers", desc="Limit and stop orders filling at live price",
         category="Orders & state", icon="hourglass-half", tone="ok", tag="No cancel", script="test_suite/pending_live_execution_runner.py",
         flags=["start", "end", "instance", "lot"], risk="safe", minutes=4),
    dict(key="advanced", name="Advanced Order Types", desc="Protection, reduce, partial close and bracket behaviour",
         category="Orders & state", icon="layer-group", tone="violet", tag="Advanced", script="test_suite/advanced_order_types_runner.py",
         flags=["start", "end", "instance"], risk="safe", minutes=3),
    dict(key="state", name="State Changes & Hedging", desc="Manual long/short coexistence and isolation",
         category="Orders & state", icon="shield-halved", tone="cyan", tag="Isolation", script="test_suite/state_changes_and_hedging_runner.py",
         flags=["start", "end", "instance"], risk="safe", minutes=3),
    dict(key="extended", name="Extended Edge Cases", desc="Odd multipliers, rounding, disabled followers, security gates",
         category="Orders & state", icon="bug", tone="warn", tag="11 tests", script="test_suite/extended_runner.py",
         flags=["start", "end", "instance"], risk="safe", minutes=4),

    # ---- Accounting ------------------------------------------------------------------
    dict(key="accounting", name="Accounting Audit", desc="Reconciles PnL, margin and equity across all accounts",
         category="Accounting & load", icon="calculator", tone="ok", tag="Audit", script="test_suite/accounting_reconciliation_runner.py",
         flags=["start", "end", "instance", "lot"], risk="safe", minutes=3),
    dict(key="jmeter", name="Load Test (Apache JMeter)", desc="Real JMeter: auth, master orders, reads, validation + SLA gates + orphan audit",
         category="Accounting & load", icon="gauge-high", tone="warn", tag="JMeter", script="test_suite/jmeter_real_runner.py",
         flags=["start", "end", "instance", "profile"], risk="safe", minutes=4),

    # ---- Security & UI ----------------------------------------------------------------
    dict(key="security", name="Security Checks", desc="Auth gates, IDOR, privilege escalation, injection, headers, CORS, rate limiting",
         category="Security & UI", icon="user-shield", tone="danger", tag="10 checks", script="test_suite/security_runner.py",
         flags=[], risk="safe", fixed_instance="paper", minutes=3),
    dict(key="ui_journey", name="Browser User Journey", desc="Real Chromium: login, terminal, tabs, logout, admin panel, mobile",
         category="Security & UI", icon="window-maximize", tone="cyan", tag="Playwright", script="test_suite/ui_journey_runner.py",
         flags=[], risk="safe", fixed_instance="paper", minutes=3),

    # ---- Real money / maintenance ----------------------------------------------------
    dict(key="real_money", name="Real-Money Certification", desc="Copy trading on the REAL instance",
         category="Real money & maintenance", icon="money-bill-transfer", tone="warn", tag="REAL MONEY",
         script="test_suite/real_money_copy_trading_runner.py", flags=["start", "end"], risk="real", fixed_instance="real", minutes=4),
    dict(key="teardown", name="Emergency Teardown", desc="Close every position and cancel every order on master + followers",
         category="Real money & maintenance", icon="trash-can", tone="danger", tag="Clean all", script=None,
         flags=["start", "end", "instance"], risk="destructive", minutes=1),
]

SUITE_INDEX: Dict[str, Dict[str, Any]] = {s["key"]: s for s in SUITES}


def public_registry() -> List[Dict[str, Any]]:
    """Registry as sent to the browser (no filesystem details beyond the script name)."""
    return [{k: v for k, v in s.items()} for s in SUITES]


def _int(v, default: int, lo: int = 1, hi: int = 100000) -> int:
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


def _num(v, default: float) -> float:
    try:
        f = float(v)
        return f if f > 0 else default
    except (TypeError, ValueError):
        return default


def build_command(suite: Dict[str, Any], params: Dict[str, Any], defaults: Dict[str, Any]) -> List[str]:
    """Turn user-chosen params into a validated argv list. Never uses a shell."""
    start = _int(params.get("start"), 1)
    end = _int(params.get("end"), defaults["follower_count"])
    if end < start:
        start, end = end, start
    instance = suite.get("fixed_instance") or (params.get("instance") if params.get("instance") in ("paper", "real") else "paper")

    if suite["key"] == "teardown":
        # run inline so the UI needs no extra script; instances: paper | real | both
        which = params.get("instance") if params.get("instance") in ("paper", "real", "both") else "paper"
        instances = ["paper", "real"] if which == "both" else [which]
        code = (
            "from test_suite.client import BlackTraderClient; "
            "from config.settings import BASE_URL, MASTER_EMAIL, DEFAULT_PREFIX, DEFAULT_DOMAIN; "
            "c = BlackTraderClient(BASE_URL); "
            f"emails = [f'{{DEFAULT_PREFIX}}{{i}}@{{DEFAULT_DOMAIN}}' for i in range({start}, {end} + 1)]; "
            f"[c.teardown_all_accounts(MASTER_EMAIL, emails, instance=i) for i in {instances!r}]; "
            "print('[+] Teardown finished for', len(emails) + 1, 'accounts')"
        )
        return [PY, "-u", "-c", code]

    cmd = [PY, "-u", suite["script"]] + list(suite.get("args") or [])
    flags = suite["flags"]
    if "start" in flags:
        cmd += ["--start", str(start)]
    if "end" in flags:
        cmd += ["--end", str(end)]
    if "instance" in flags:
        cmd += ["--instance", instance]
    if "lot" in flags:
        cmd += ["--lot", str(_num(params.get("lot"), 0.1))]
    if "orders_count" in flags:
        cmd += ["--orders-count", str(_int(params.get("orders_count"), 10, 1, 500))]
    if "burst" in flags:
        cmd += ["--burst", str(_int(params.get("burst"), 10, 1, 500))]
    if "profile" in flags:
        prof = params.get("profile") if params.get("profile") in ("smoke", "standard", "stress") else "standard"
        cmd += ["--profile", prof]
    if "only" in flags and params.get("only"):
        steps = [s.strip().upper() for s in str(params["only"]).split(",")]
        steps = [s for s in steps if re.fullmatch(r"E\d{2}", s)][:15]
        if steps:
            cmd += ["--only", ",".join(steps)]
    if "ramp" in flags:
        raw = str(params.get("ramp") or "10,25,50,100")
        levels = [str(_int(x, 10, 1, 500)) for x in raw.split(",") if x.strip()][:8]
        cmd += ["--ramp", ",".join(levels) or "10,25,50"]
    return cmd


def effective_instance(suite: Dict[str, Any], params: Dict[str, Any]) -> Optional[str]:
    return suite.get("fixed_instance") or params.get("instance") or "paper"


def needs_confirmation(suite: Dict[str, Any], params: Dict[str, Any]) -> bool:
    inst = effective_instance(suite, params)
    return suite["risk"] in ("real", "destructive") or inst in ("real", "both")
