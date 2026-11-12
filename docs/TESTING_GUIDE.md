# Testing Guide

How the suite is organised, how to read results, and how to extend it.

## Mental model

```
dashboard (Flask)  ──launches──▶  test_suite/*_runner.py  ──HTTP──▶  BlackTrader OMS
      │                                   │
      │ reads                             │ writes
      ▼                                   ▼
reports/logs (live log, run history)   reports/evidence (JSON + Markdown)
```

* **One shared client** – `test_suite/client.py` (`BlackTraderClient`) handles logins, token caching,
  retries and every OMS call (orders, positions, protection, squareoff, reduce, copy settings).
* **One runner per suite** – each is a standalone script with `argparse` (`--start --end --instance ...`),
  prints `[PASS]` / `[FAIL]` lines and writes an evidence file.
* **One registry** – `dashboard/suites.py` lists every suite; the launcher UI and the command line the
  dashboard executes are generated from it.

## Account topology

* 1 **master** (`MASTER_EMAIL`) whose orders are copied.
* N **followers** named `<prefix><n>@<domain>`, `n = 1..FOLLOWER_COUNT`.
* Two broker **instances**: `paper` (hedging, simulated) and `real`.
* Copy modes: *multiplier* (fixed), *balance-based* and *equity-based* sizing.

Start small: `--end 10` is enough to iterate; use all followers before a release.

## Reading a result

Every suite prints a verdict per scenario and a summary, then writes
`reports/evidence/<suite>_<YYYYMMDD_HHMMSS>.json|md`. The dashboard's header cards count the **latest**
evidence file of each suite family.

The **Breakpoint & Race Hunter** uses severities:

| Severity | Meaning | Verdict |
|---|---|---|
| `HIGH` | An invariant was violated (a real bug) | FAIL |
| `MED` | Suspicious or non-idempotent behaviour worth a look | WARN |
| `INFO` | A measurement (e.g. the load-ramp degradation point) | – |

### Breakpoint & Race Hunter checks

| ID | Invariant |
|---|---|
| B1 | N concurrent closes of one position close it **once** and credit PnL **once** |
| B2 | Concurrent partial closes never drive quantity negative or flip the side |
| B3 | Concurrent TP/SL updates leave a TP and SL from the **same** write (no torn pair) |
| B4 | Concurrent cancels of one order never 5xx and leave nothing pending |
| B5 | Load ramp (10/25/50/100 concurrent master orders): no missing or duplicate fan-out; reports latency and fan-out lag |
| B6 | Follow/unfollow flapping never creates duplicate links (no double fan-out) |
| B7 | A low-balance follower never ends with `used_margin > equity` |
| B8 | Hostile payloads (zero/negative/NaN/huge qty, bad type, injection strings) get 4xx, never 5xx, never a position |
| B9 | Bulk close racing single closes leaves 0 positions and 0 margin |
| B10 | Parallel forced re-logins leave every session valid |
| B11 | After teardown: 0 positions, 0 pending orders, 0 margin, equity == balance on every account |

### End-to-End Test

`test_suite/e2e_runner.py` — the suite to run first on every build. Steps run in order; each prints
`[PASS]`/`[WARN]`/`[FAIL]`/`[SKIP]` and the run writes `reports/evidence/e2e_evidence_<ts>.json|md`
(rendered in the dashboard's **End-to-end** tab).

Expected follower size after every master action: `net_qty(follower) = net_qty(master) × factor`, where factor is the
link's multiplier (× balance or equity ratio for those methods, negative when reverse). Followers are polled for up to 25 s.

| ID | Step | Fails when |
|---|---|---|
| E01 | Preflight | platform down, admin/master/follower login fails |
| E02 | Copy topology | no follower in range is linked (unlinked ones are a WARN and excluded) |
| E03 | Clean slate | teardown leaves positions or pending orders |
| E04 | Baseline | margin in use with no positions |
| E05 | Open & fan-out | a follower does not open master qty × factor; sampled copy orders lack a `copy_ref` to the master (WARN) |
| E06 / E07 | Set / modify TP/SL | a follower's TP/SL trigger differs from the master's |
| E08 | Partial close | followers do not reduce proportionally |
| E09 | Pyramid + hedge | add-on BUY or hedge SELL leg not mirrored |
| E10 | Close one position | followers keep the closed leg or lose the other one |
| E11 | Close all | any account keeps a position or margin |
| E12 | Pending orders | a far LIMIT/STOP creates a position, or pending orders survive the master's cancel |
| E13 | Every market type | one symbol per market group is not copied, not closed everywhere, or has wrong PnL (closed markets: INFO) |
| E14 | Input validation | qty 0 / negative / unknown symbol / bad side is accepted or returns 5xx |
| E15 | Accounting | a trade's `realized_pnl` ≠ (exit − entry) × qty × contract size, or balance moved by something other than realized PnL |
| E16 | Final audit | positions, pending orders, margin or equity ≠ balance left on any account |

Options: `--start/--end` (followers), `--lot` (master opens 2× lot, then reduces/adds/hedges 1× lot),
`--only E05,E06` (setup E01–E04 and the final audit E16 always run), `--instance real --i-understand-real-money`.

### Symbol coverage

`test_suite/symbol_coverage_runner.py` reads the platform's symbol universe from `symbol_url` in `GET /api/config`
(today `https://terminal.blacktrader.com/feed/symbol_list`, 3 643 markets) and, in batches of 20, has the master open a
market BUY of **2 × the symbol's quantity step** on each, checks every linked follower holds master qty × factor, closes,
checks everyone is flat, and checks realized PnL on the master and one follower per distinct multiplier.

| Verdict | Meaning |
|---|---|
| PASS | copied at the right size, closed everywhere, PnL correct |
| FAIL | copy missing / wrong size, follower not flat after close, PnL wrong, or a 5xx |
| WARN | the master order was rejected for a reason other than "market closed", or a data feed (GREEKS) accepted an order |
| SKIP | `market closed for <symbol>` – re-run in that market's session |

**Order size.** 2 × max(qty step, min qty), so a 0.5x follower's copy is still a valid size.

**PnL rule.** `precisionMap[symbol][3]` is `1` or `[kind, _, contract_size, conversion_symbol]`. For `type1`, and `type3`
quoted in USD (EURUSD), PnL = (exit − entry) × qty × contract_size exactly (XAUUSD ×100, EURUSD ×100 000, XAGUSD ×5 000).
Pairs whose quote currency is not USD (`type2` USDJPY, `type3` crosses GBPJPY / EURGBP, `type4` crosses CADCHF / CHFJPY) are converted at a live rate the
history row does not carry; for them the check is: PnL has the sign of the price move, and PnL per unit of move is the
same on master and followers. Observed 2026-11-12: those pairs use 100 000 units per lot although the feed lists 1 000.

Market sessions (UTC, from the feed's `typeMap`): NSE/BSE stocks, futures, options, indices 03:45–10:00 Mon–Fri;
EU stocks 07:00–15:30; US stocks 13:30–20:00 (summer; one hour later in winter); forex/metals/commodities/indices nearly 24×5;
crypto and `.247` CFDs 24×7. About 2 700 of the 3 643 symbols are Indian, so run **All Symbols** inside the Indian session for full coverage.

Run time is dominated by `GET /orders`, which returns an account's **entire** order history (6 000+ orders, no paging or
filter), so pending-order checks cost ~1–2 s per account. That is also why the `copy_ref` check samples 12 followers.

### Complex Copy Scenarios (model-based)

Followers are split into cohorts with different copy rules (multiplier 2x/1x/0.5x, balance-based, equity-based,
reverse). After every master action the suite checks each follower's **net signed quantity** against
`master_net * factor` (factor = multiplier, balance ratio, equity ratio, or negative for reverse).

| ID | Scenario |
|---|---|
| X1 | Mixed-mode sizing side by side |
| X2 | Reverse followers open the opposite side; PnL signs are opposite |
| X3 | Pyramiding, partial reduces, hedge legs, single closes - checked after each step |
| X4 | TP/SL set and modified 3x on the master reach every follower unchanged |
| X5 | A follower closes its copy / trades on its own: still copies new trades, own trade survives master close |
| X6 | Multiplier changed mid-trade: open position untouched, next order uses the new multiplier |
| X7 | Far pending orders placed and cancelled: no positions or leftover pendings on followers |
| X8 | Rapid open/close churn: everyone flat, no stuck margin, identical followers identical PnL |
| X9 | Protection + reduce + two new orders fired concurrently, then model check (5 rounds) |
| X10 | Seeded random open/reduce/close/protect walk; reproduce a failure with `--only X10 --seed N` |

## Load testing with Apache JMeter

```bash
python scripts/install_jmeter.py                       # once: JMeter 5.6.3 (+ Java 17 if missing) into ~/tools, checksum-verified
python test_suite/jmeter_real_runner.py --profile smoke --end 20       # ~1 min sanity check
python test_suite/jmeter_real_runner.py --profile standard --end 100   # launch-day load: the one to gate on
python test_suite/jmeter_real_runner.py --profile stress --end 100     # find where it degrades
```

The plan (`tests/jmeter/blacktrader_oms_load_test.jmx`, generated by `tests/jmeter/build_plan.py`) runs five groups in sequence:
real two-step login + chart-token; master **place + close** market order (fans out to every follower); follower
**position reads**; unpaginated **order history** reads; **negative** requests that must return 4xx.

| Profile | Auth | Master orders | Follower reads | History |
|---|---|---|---|---|
| smoke | 5 x 2 | 5 x 2 | 10 threads, 15s | 2 x 2 |
| standard | 20 x 3 | 20 x 5 | 50 threads, 30s | 5 x 3 |
| stress | 40 x 3 | 50 x 4 | 100 threads, 60s | 10 x 3 |

What the runner checks (each is a PASS/FAIL line in the evidence):
* **Error rate** per request type <= 1% and **p95 latency** within an SLA (defaults in `SLA_P95_MS`; override with `--sla "ORDER place market=3000"`).
  The defaults are *our* choice (ceiling taken from measured behaviour), not a platform commitment - set your own.
* **Validation**: invalid input must be rejected with 4xx. Two labels are known platform bugs and fail until fixed.
* **Integrity audit** after the load: every copied position must be closed (no orphan positions or stuck margin).

Outputs: `reports/evidence/jmeter_real_evidence_<ts>.json|md` and JMeter's own HTML dashboard in `reports/jmeter/<ts>/html/index.html`
(git-ignored). Tokens and the member password are written only to a temp folder for the run and scrubbed from kept logs.
Do **not** run a load test while another suite is running - they share the same accounts and corrupt each other.
Files in `reports/evidence/simulated/` come from the retired Python simulation, not JMeter.

## Safety model

| Action | Guard |
|---|---|
| Real-money suite, any suite on `real`, teardown | Dashboard asks to type `REAL` / `TEARDOWN`; API returns `412` without `confirm: true` |
| CLI runner on a non-paper instance | `breakpoint_race_runner.py` requires `--i-understand-real-money` |
| Two runs at once | Dashboard returns `409` |
| Dashboard exposure | localhost only, or `DASHBOARD_TOKEN` |

Suites are written to be **idempotent**: they tear down before and after. If a run is stopped midway,
use **Emergency Teardown**.

## Adding a new suite

1. **Write the runner** in `test_suite/my_suite_runner.py`. Minimum shape:

   ```python
   import argparse, sys
   from pathlib import Path
   sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
   from config.settings import BASE_URL, DEFAULT_PREFIX, DEFAULT_DOMAIN, MASTER_EMAIL, MASTER_ID, FOLLOWER_COUNT
   from test_suite.client import BlackTraderClient

   def main():
       ap = argparse.ArgumentParser()
       ap.add_argument("--start", type=int, default=1)
       ap.add_argument("--end", type=int, default=FOLLOWER_COUNT)
       ap.add_argument("--instance", default="paper")
       a = ap.parse_args()
       emails = [f"{DEFAULT_PREFIX}{i}@{DEFAULT_DOMAIN}" for i in range(a.start, a.end + 1)]
       c = BlackTraderClient(BASE_URL)
       c.teardown_all_accounts(MASTER_EMAIL, emails, a.instance)
       ...                                   # act, then assert invariants
       print("[PASS] my check")              # the dashboard counts these markers
       c.teardown_all_accounts(MASTER_EMAIL, emails, a.instance)

   if __name__ == "__main__":
       main()
   ```
   Never hardcode the master or follower emails – use the settings above.

2. **Register it** – add one dict to `SUITES` in `dashboard/suites.py` (name, description, category,
   icon, `script`, supported `flags`, `risk`). It appears in the launcher immediately.

3. **Write evidence** – dump a JSON where each scenario is a dict containing `"status": "PASS" | "FAIL"`
   to `reports/evidence/my_suite_<timestamp>.json`; the header cards pick it up automatically.

4. **Run the smoke tests** – `python -m pytest -q`. They verify the registry points at real files, that every
   flag you declared is accepted by the runner, and that the module imports.

## Known platform findings (from the Breakpoint Hunter)

* **NEW (observed 2026-11-12 evening): paper copy links can no longer be created, only ended.**
  `POST /copy/follow` for a follower with no active paper link returns HTTP 400
  *"Copy trading, MAM and PAMM run on real-money accounts. A paper relationship that already exists can still be ended here."*
  Updating an existing active link (e.g. changing the multiplier) still works. **Do not unfollow paper followers in tests** -
  the link cannot be re-created. Scenarios that unfollow then re-follow (Breakpoint B6, Race "unfollow vs order", Extended bulk
  unfollow/re-follow) will permanently drop followers until the platform allows it again.

* **Sub-minimum copies are rounded UP (observed 2026-11-12, Symbol Coverage).** `BLACK:US30cash-1` has min qty 1 and step 0.1;
  a master order of 1 was copied to 0.5x followers as **1.0**, not 0.5 - those followers carry double their intended
  exposure. Whether to round up, skip or reject a copy below the symbol minimum is a product decision; it is not flagged by
  the suites (they size orders so every copy is above the minimum).
* First full **All Symbols** run (2026-11-12, 17:06–17:26 UTC, 99 followers): 820 / 820 open symbols copied, closed and
  accounted correctly after the test's contract-spec fixes; 2 823 skipped as closed (all NSE/BSE, EU stocks, GREEKS).
  NSE/BSE symbols (2 690) and EU stocks still need a run inside their sessions.
* `POST /v1/oms/{instance}/orders` with an unknown `type` returns **500** instead of 400.
* Absurd protection values (`tp=-1`, `sl=1e30`) on a market order are **accepted**.
* `GET /orders` returns the full order history with no pagination (grows without bound). Verified 2026-11-12: `limit`,
  `state`, `status`, `page_size` and `per_page` query parameters are all ignored (6 361 orders returned for follower1).
* `BlackTraderClient` retries POSTs on 5xx; if the server executes an order and then errors, the retry could
  duplicate it. Treat unexplained duplicate orders in evidence with that in mind.

## Troubleshooting runs

* Live log is `reports/logs/live_execution.log`; every finished run is archived in `reports/logs/runs/`.
* A suite that hangs: **Stop** in the dashboard, then **Emergency Teardown**.
* Rate limiting (HTTP 429): lower `--end`, or the client's `max_workers`.
