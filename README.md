# BlackTrader Automation & Copy-Trading Test Suite

Automated testing for the **BlackTrader / BlackFX** copy-trading OMS (`lpadmin.blackfx.com`):
a 100-follower fan-out test suite, a race-condition / breakpoint hunter, and a web dashboard
(**Test Hub**) to launch suites, watch them live and browse the evidence.

> **Safe by default.** Everything runs on the **paper** instance. Anything that touches the
> **real** instance, or that closes positions everywhere, needs a typed confirmation.

---

## Quickstart (3 minutes)

```bash
git clone <this-repo> && cd lpadmin
python scripts/bootstrap.py        # venv + dependencies + .env from template
# edit .env: ADMIN_*, MEMBER_PASSWORD, MASTER_EMAIL, MASTER_ID
python scripts/doctor.py           # verifies install, credentials, login, accounts
python dashboard/app.py            # open http://localhost:5000
```

In the dashboard: press **End-to-End Test** (top of the launcher), or **Quick run** on the **E2E Report** tab.
Output streams live; the step-by-step verdict appears in **E2E Report**, and every run lands in **History** and **Evidence**.

No dashboard? Same thing from the terminal:

```bash
python test_suite/e2e_runner.py --end 10          # ~3 min; all followers: ~10 min
python test_suite/e2e_runner.py --only E06        # re-check one step (setup + final audit always run)
```

### End-to-End test (start here)
One run takes a copied trade through its whole life and checks the master **and every linked follower** after each step:
open & fan-out → set TP/SL → modify TP/SL → partial close → pyramid + hedge → close one leg → close all →
pending orders place/cancel → **one symbol of every market type** → invalid input rejected → accounting reconciles →
final clean-account audit (E01–E16).

### Symbols
The platform lists ~3 600 symbols (its `symbol_url`: Binance crypto, forex, metals, commodities, CFDs, US/EU stocks,
indices, NSE/BSE stocks, futures and options). **Market Types Check** trades one per market group (~2 min);
**All Symbols** trades every one (~1 h on 100 followers). Closed markets are SKIPPED, so run again during their session.

```bash
python test_suite/symbol_coverage_runner.py --sample --end 10        # one per market group
python test_suite/symbol_coverage_runner.py --end 10                 # every symbol
python test_suite/symbol_coverage_runner.py --types FOREX,METAL      # chosen market types
```
Followers without an active copy link are listed as a **WARN** and left out of the checks
(paper copy links can no longer be re-created on the platform). Details: [docs/TESTING_GUIDE.md](docs/TESTING_GUIDE.md#end-to-end-test).

### What you need before you start
| Need | Details |
|---|---|
| Python 3.9+ | `python --version` |
| Admin login for lpadmin | `ADMIN_EMAIL` / `ADMIN_PASSWORD` |
| A master trader account | its email + `mem_...` client id (shown in the admin panel) |
| Follower accounts | `follower1..N@mailinator.com`; create them with `python main.py create --start 1 --end 100` |

`python scripts/doctor.py` tells you exactly which of these is missing and how to fix it.
The dashboard shows the same checks under **Getting Started**.

---

## Configuration (`.env`)

Copy `.env.example` to `.env` (git-ignored). Full list:

| Variable | Default | Meaning |
|---|---|---|
| `BASE_URL` | `https://lpadmin.blackfx.com` | Platform to test |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | – | Admin API login (required) |
| `MEMBER_PASSWORD` | – | Shared password of master + followers (required) |
| `MASTER_EMAIL`, `MASTER_ID` | – | The master (leader) account |
| `DEFAULT_EMAIL_PREFIX`, `DEFAULT_EMAIL_DOMAIN` | `follower`, `mailinator.com` | Follower naming: `<prefix><n>@<domain>` |
| `FOLLOWER_COUNT` | `100` | How many followers exist |
| `DASHBOARD_HOST`, `DASHBOARD_PORT` | `127.0.0.1`, `5000` | Dashboard bind address |
| `DASHBOARD_TOKEN` | empty | Required to expose the dashboard beyond localhost |

---

## The dashboard (Test Hub)

`python dashboard/app.py` -> http://localhost:5000

| Area | What it does |
|---|---|
| **Launcher** (left) | All suites grouped by purpose. Options: paper/real, follower range, lot, orders, load ramp. Press `/` to filter. |
| **Regression** | Runs a preset (Smoke ~5 min / Standard ~25 min / Full ~1 h) or hand-picked safe suites back to back on paper, then gives one downloadable HTML report (suites, E2E steps, market groups). Other launches are blocked while it runs. |
| **Dispatch** | Send one master order on **any of the ~3 600 symbols** (search box shows market, min/step/max, contract size), MARKET / LIMIT / STOP with optional TP/SL; compares every linked follower's copy (size, side, fill, latency on server time; unlinked followers shown as NOT LINKED). **Close master & verify flat** closes everything and checks every follower followed. |
| **Markets open now** (E2E Report tab) | Which market types are in session per the platform schedule, and how many symbols are tradable right now. |
| **E2E Report** | The latest End-to-End verdict as a step checklist. Failed steps open by themselves; each has **Re-run this step** and **Copy bug report** (ready-to-paste ticket with the reproduce command). Earlier runs are in the picker. |
| **Summary cards** | Computed from real evidence files and run history (not static numbers). |
| **Terminal** | Live log with `PASS`/`FAIL` counters, copy and download. |
| **Followers / Order Flow / Dispatch** | Live account grid, order tape, and "send one master order and verify all followers". |
| **Evidence** | Every JSON/Markdown report the suites produced. |
| **History** | Every run from the dashboard with its archived log and a one-click re-run. |
| **Book pill** (header) | Shows each account's routing and opens the **A-book / B-book switch** (per account: master, a follower range, or all). Typed confirmation, blocked during a run, read-back verified. Real-instance routing only. |
| **Getting Started** | The setup doctor with a fix for each failing check. |

**Safety rails:** real-money suites and Emergency Teardown require typing a confirmation word;
only one run at a time; the dashboard answers only on `localhost` unless `DASHBOARD_TOKEN` is set
(`http://host:5000/?token=...`, once per browser).

**Sharing it with teammates:** set `DASHBOARD_HOST=0.0.0.0` and a long random `DASHBOARD_TOKEN`
in `.env`. The dashboard refuses to start on a non-local address without a token.

---

## Test suites

| Suite | Proves | Time |
|---|---|---|
| **End-to-End Test** | Full trade lifecycle on master + every linked follower, every market type, accounting and clean-up (E01–E16) | ~3 min (10 followers) / ~10 min (100) |
| **Market Types Check** | One symbol of each of the 18 market groups: copied at the right size, closed everywhere, correct PnL | ~2 min |
| **All Symbols** | The same for every listed symbol (~3 600); closed markets skipped | ~1 h (100 followers) |
| Multiplier / Balance / Equity mode | Position sizing for each copy mode across followers | ~4 min |
| Buy/Sell parity & Stop | Market/limit/stop orders behave identically both ways | ~3 min |
| Paper 2x certification | 10 lot master -> 20 lot follower end to end | ~3 min |
| **Complex Copy Scenarios** | Model-checked cohorts (multiplier / balance / equity / reverse): pyramiding, partial closes, TP/SL sync, follower intervention, mid-trade multiplier change, phantom copies, churn, concurrent chained ops, seeded random walk | ~8 min |
| **Breakpoint & Race Hunter** | Double-close/double-credit, over-reduce, torn TP/SL, double-cancel, load ramp, follow/unfollow flapping, margin exhaustion, hostile input, bulk-vs-single close, auth storm, final audit | ~6 min |
| Race conditions | Flash trades, dual orders, 10-thread storm, unfollow race | ~3 min |
| Extreme scenarios | Rapid reversal, capital shock, straddle, micro-lots | ~5 min |
| Trigger vs modify/cancel | Pending trigger racing cancel and TP/SL edits | ~4 min |
| Pending live triggers, Advanced orders, State & hedging, Extended edge cases | Order-type and state-isolation coverage | 3-4 min each |
| Accounting audit | PnL, margin and equity reconcile across all accounts | ~3 min |
| **Load test (Apache JMeter)** | Real JMeter 5.6: login/token, master place+close with fan-out, follower reads, order history, validation; p95/error SLA gates + post-load orphan audit | ~4 min |
| **Real-money certification** | Copy trading on the **real** instance | ~4 min |
| **Emergency teardown** | Closes every position / cancels every order | ~1 min |

Details, how to read a report, and how to add a suite: **[docs/TESTING_GUIDE.md](docs/TESTING_GUIDE.md)**.

Run any suite from the terminal, e.g.:

```bash
python test_suite/race_conditions_runner.py --start 1 --end 20
python test_suite/breakpoint_race_runner.py --end 100 --ramp 10,25,50,100,200
python test_suite/breakpoint_race_runner.py --only B1,B5
```

Each run writes `reports/evidence/<suite>_<timestamp>.json` + `.md`.

---

## Account management CLI (`main.py`)

```bash
python main.py list-masters
python main.py create --start 1 --end 100                  # create + fund followers (headless browser)
python main.py create --headed --start 1 --end 10          # watch the browser
python main.py follow --master "ctmaster" --start 1 --end 100 --multiplier 2.0
python main.py follow --master "ctmaster" --instance both --reverse --start 1 --end 50
```
Needs `playwright install chromium`. HTTP-only equivalents live in `scripts/api_*.py`.

---

## Repository map

```
config/            settings.py (.env loader), doctor.py (setup checks)
dashboard/         app.py (Flask API), suites.py (suite registry), templates/, static/
test_suite/        client.py (HTTP client) + one *_runner.py per suite
scripts/           bootstrap.py, doctor.py, api_*.py, playwright_*.py
tests/             test_smoke.py (offline, no credentials), jmeter/ plan
reports/evidence/  generated evidence (JSON + Markdown + screenshots)
reports/logs/      live log, per-run archive and run history (git-ignored)
docs/              TESTING_GUIDE.md, API_DOCUMENTATION.md
```
Root-level `create_accounts.py`, `follow_master.py`, `playwright_*.py` are older copies kept for
backwards compatibility; prefer `main.py` and `scripts/`.

---

## Development

```bash
python -m pytest -q          # offline smoke tests, ~1 second, no credentials needed
```
CI (`.github/workflows/ci.yml`) runs the same on every push.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Dashboard shows "Setup incomplete" | Open **Getting Started**; each failing check lists its fix |
| `ModuleNotFoundError: flask` | `pip install -r requirements.txt` (or `python scripts/bootstrap.py`) |
| `Admin login failed: HTTP 401` | Check `ADMIN_EMAIL` / `ADMIN_PASSWORD` in `.env` |
| Master login fails | Set `MASTER_EMAIL`, `MASTER_ID`, and `MEMBER_PASSWORD` |
| "Follower accounts exist (12/100)" | `python main.py create --start 1 --end 100`, or lower `FOLLOWER_COUNT` |
| Dashboard 403 / 401 from another machine | Set `DASHBOARD_TOKEN` and open `/?token=...` |
| A run was stopped midway | Use **Emergency Teardown** to close leftover positions |
| Port 5000 busy | `DASHBOARD_PORT=5050` in `.env` |

## Security notes
- `.env` is git-ignored. Never commit credentials; `.env.example` holds placeholders only.
- Evidence reports are committed; skim them for account identifiers before publishing the repo.
- The dashboard can place and close trades. Keep it on localhost, or behind `DASHBOARD_TOKEN`.
