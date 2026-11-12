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

In the dashboard: pick **Breakpoint & Race Hunter**, set followers `1` to `10`, press it.
Output streams live; results land in **History** and **Evidence**.

No dashboard? Same thing from the terminal:

```bash
python test_suite/breakpoint_race_runner.py --end 10
```

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
