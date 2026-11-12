# Prompt: build a PAMM test dashboard (same pattern as the copy-trading Test Hub)

Copy everything below the line into your AI coding agent, opened in the PAMM project folder.
Fill in the `<<...>>` placeholders first (or leave them and let the agent ask).

---

You are working in an existing project folder for a **PAMM (Percent Allocation Management Module)**
trading product on the BlackTrader platform. Build an automated **test suite + web dashboard ("PAMM Test Hub")**
that tests the PAMM system end to end, finds how it breaks, and lets other people run it easily.

I already built the same thing for copy trading (a Flask dashboard, a suite registry, one runner script per
suite, evidence reports, a setup doctor, smoke tests, CI, docs). Re-create that proven architecture for PAMM,
adapted to PAMM's rules. Work in phases and verify each phase before moving on. Do not skip the discovery phase.

## 0. Context I will give you (ask me if anything is missing)

- Platform URL: `<<https://...>>`  | Admin login: `<<email>>` (password goes in `.env`, never in code)
- PAMM manager account: `<<email, id>>`  | Investor accounts: `<<prefix/domain, count e.g. investor1..50@mailinator.com>>`
- Instances: `<<paper/demo and real>>`  -> **default and test everything on paper/demo only.**
- Any API docs, Postman collection or frontend bundle I can point you to: `<<path/URL>>`

## 1. Phase 1 - Discovery (before writing any code)

1. Read the whole folder. Summarise the architecture, existing scripts and conventions in 15 lines.
2. Discover the PAMM API: login flows (admin / manager / investor), and every endpoint for creating a PAMM
   account, investor allocation/deposit, withdrawal, share/NAV queries, trade placement by the manager,
   fee configuration, settlement/rollover, and reports. If there are no docs, inspect the web app's network calls
   or frontend JavaScript (Playwright is fine) and **write what you found to `docs/API_DOCUMENTATION.md`**.
3. Write down the PAMM **business rules you can verify**, and ask me about any you cannot, for example:
   allocation method (pro-rata by equity / by balance / by share), management fee and performance fee,
   high-water mark, settlement period (daily/weekly/on-close), minimum deposit, lot rounding, what happens to
   investor deposits/withdrawals while trades are open, manager stop-out/drawdown rules, investor equity vs balance.
4. Show me the plan (suites, files, risks) and wait for my OK before Phase 2.

## 2. Architecture to reproduce (mirror this layout)

```
config/settings.py      .env loader (BASE_URL, ADMIN_*, MEMBER_PASSWORD, MANAGER_EMAIL, MANAGER_ID,
                        INVESTOR_PREFIX/DOMAIN/COUNT, DASHBOARD_HOST/PORT/TOKEN). NO hardcoded identities anywhere.
config/doctor.py        setup checks used by CLI and dashboard: python version, packages, .env present,
                        credentials not placeholders, platform reachable, admin login, manager login,
                        investor accounts exist. Never echo secrets. Each failure returns a concrete fix.
scripts/bootstrap.py    one command: venv + pip install + .env from .env.example + offline doctor
scripts/doctor.py       CLI for the checks (exit code 1 if not ready)
test_suite/client.py    ONE thread-safe HTTP client: token cache, retries, helpers for every PAMM call.
                        IMPORTANT: do NOT auto-retry POSTs on 5xx (a retry can duplicate an allocation/withdrawal).
test_suite/*_runner.py  one standalone argparse script per suite (--start --end --instance ...);
                        prints [PASS]/[FAIL] markers; writes reports/evidence/<suite>_<timestamp>.json + .md
dashboard/suites.py     SUITE REGISTRY = single source of truth (key, name, desc, category, icon, tone, tag,
                        script, flags, risk: safe|real|destructive, fixed_instance, minutes). The launcher UI and
                        the command line are generated from it. Adding a suite = writing a runner + one entry.
dashboard/app.py        Flask API (see section 4)
dashboard/templates/    single-page UI (see section 5)
tests/test_smoke.py     offline tests (no network/credentials), pytest.ini with testpaths=tests
.github/workflows/ci.yml  compileall + pytest on push (py 3.9 and 3.12)
README.md, docs/TESTING_GUIDE.md, .env.example, requirements.txt (include flask), .gitignore (.env, reports/logs/)
```

## 3. Test suites to build (PAMM-specific)

Use **model-based testing**: after every action, compute what PAMM *should* do and compare against the real state
of the manager and every investor. Split investors into **cohorts** with different capital / allocation settings,
define a `factor` per investor (their share of the pool), and assert
`investor_net_position == manager_net_position * factor` (and the money equivalents) after each step,
polling until converged (report the convergence lag).

Core suites (each is one runner):
1. **Allocation sizing** - manager opens/closes trades; investors with different balances/equity/shares receive
   exactly pro-rata positions. Cohorts: tiny, small, equal, large, whale. Check lot rounding is deterministic.
2. **Pyramid + partial cascade** - adds, partial closes, hedge legs, single closes; verify every investor after each step.
3. **Deposit / withdrawal while trades are open** - share/NAV must not be diluted or inflated; late investors do not
   receive retroactive profit; withdrawn capital is excluded from later allocations.
4. **Fees & profit sharing** - management fee, performance fee, high-water mark; reconcile: manager fee + all investor
   PnL = total pool PnL (conservation of money, tolerance for rounding). Include loss-then-recovery (HWM) cases.
5. **Settlement / rollover** - run settlement and verify balances, shares, fee charged exactly once, no double settlement
   when triggered twice or concurrently.
6. **Manager actions** - TP/SL set and modified, pending orders (limit/stop) placed/cancelled, modify while filling:
   investors get identical protection levels; no phantom allocations from cancelled orders.
7. **Investor interventions & isolation** - investor leaves/pauses mid-trade, investor tries to trade or close
   manager-controlled positions (must be rejected), disabled investor is skipped, re-enabled investor is not retro-allocated.
8. **Risk limits** - manager drawdown / stop-out, insufficient margin on small investors (partial/none, never negative
   balance, never over-leverage), minimum deposit enforcement.
9. **Accounting audit** - after teardown: zero positions, zero pending orders, margin 0, equity == balance, shares sum
   to 100%, total pool value equals sum of investor values.
10. **Seeded random walk** - random sequence of manager trades, investor deposits/withdrawals, protection edits;
    model-checked at checkpoints; reproducible with `--seed N`; print the op log on failure.

**Breakpoint & Race Hunter** (a separate runner; its job is to BREAK the system). Each check states an invariant:
- N concurrent withdrawals of the same investor -> processed once, never more than their balance
- N concurrent deposits / duplicate deposit request -> credited once (test idempotency with identical payloads)
- Withdraw racing a manager close or a settlement -> no negative balance, no lost money, fee charged once
- Concurrent settlement triggers -> exactly one settlement
- Concurrent investor join/leave flapping -> no duplicate membership rows (=> no double allocation)
- Manager burst of orders (ramp 10/25/50/100 concurrent) -> no missing/duplicate investor allocations; report p50/p95 latency
  and fan-out lag; stop ramping when correctness breaks and report the first degradation point
- Hostile input fuzz (zero/negative/NaN/inf/huge amounts, wrong types, unknown ids, injection strings, missing fields)
  -> only 4xx, never 5xx, never a state change
- Margin/amount exhaustion with tiny investors; token-refresh storm; bulk vs single close race
- Final consistency audit (as in suite 9)
Severity model: `HIGH` = invariant violated (bug) -> FAIL; `MED` = suspicious/non-idempotent -> WARN; `INFO` = measurement.
Require `--i-understand-real-money` for any non-paper instance.

For every suite: tear down before and after, restore any account settings/balances you changed (in a `finally`),
never hardcode emails/ids, and make runs repeatable.

## 4. Dashboard backend (Flask)

- Endpoints: `/api/config` (non-secret config only), `/api/suites` (registry), `/api/health` (runs the doctor, cached ~20s,
  `?refresh=1`), `/api/status`, `/api/logs`, `/api/logs/download`, `/api/run`, `/api/stop`, `/api/history`,
  `/api/history/<id>/log`, `/api/summary` (real stats computed from the latest evidence per suite + run history),
  `/api/reports`, `/api/reports/<file>`, `/api/screenshots`, plus live-account endpoints for the manager and investors.
- `/api/run`: accepts `{suite, params, confirm}`; builds the command line **from the registry with validated params**
  (clamp ints, whitelist instance, never use a shell); one run at a time (409); returns **412 `needs_confirmation`**
  for real-instance or destructive suites unless `confirm: true`. Start subprocesses with `-u`, `PYTHONUNBUFFERED=1`,
  `PYTHONIOENCODING=utf-8` so logs stream live. A stopped run must stay `TERMINATED`, not become `FAILED`.
- Persist run history in `reports/logs/run_history.json` and archive each run's log in `reports/logs/runs/<id>.log`.
- Access control: bind to 127.0.0.1 by default; reject non-localhost Host headers (DNS-rebinding defence) unless
  `DASHBOARD_TOKEN` is set; with a token accept `?token=` once (set an HttpOnly cookie), header or cookie; refuse to
  start on a non-loopback host without a token.
- `/api/config` must never leak passwords/tokens (write a test for it).

## 5. Dashboard UI/UX (single page, dark theme matching the platform)

- Left **launcher**: suites grouped by category, generated from the registry; "Run on: Paper | Real" switch (Real tints
  the panel red); investor range from/to; Advanced (amounts/lots, orders, load ramp); live hint ("N investors + manager on
  PAPER"); filter box (press `/`); suites disabled while a run is active; risk badge colours.
- **Summary cards computed from real data**: suites green x/y, checks passed/failed, last run (name, status, relative time),
  target (investor count + manager), setup status (click opens the setup tab). **No static/fake numbers.**
- Tabs (labels on one line, scrollable): Terminal, Investors grid (live, with per-account drawer: positions, orders,
  balance, share %, PnL), Order flow tape, Evidence, Manager dispatch & verify (place one manager order and compare every
  investor's allocation to the expected value in a table), Screenshots, History (re-run button, log viewer), Getting Started.
- **Terminal**: live log with `[PASS]`/`[FAIL]`/`[HIGH]`/`[MED]` highlighting (escape HTML first; don't re-render if text
  unchanged so selection survives), live PASS/FAIL counters, progress bar, Copy, Download, helpful empty state.
- **Getting Started**: doctor results with a copyable fix per failing check, 4-step first-run guide and a one-click
  "safe first run" (e.g. 10 investors, paper). Show a banner on every tab if setup is incomplete; open this tab
  automatically when the doctor fails.
- **Safety UX**: typed-word confirmation modal (`REAL` / `TEARDOWN`) for real-money and destructive suites, Esc closes,
  Stop asks for confirmation and reminds to run Emergency Teardown.
- Polling: only poll the visible tab and only when the page is visible (do not hit 100 accounts every 3s in the background).
  Toasts for completion with pass/fail counts; document title shows the running suite.
- Responsive down to phone width (no horizontal page scroll), keyboard accessible, `prefers-reduced-motion` respected.

## 6. Onboarding for other people / new clones

- `python scripts/bootstrap.py` then `python scripts/doctor.py` then `python dashboard/app.py` must work on a fresh clone
  with only a filled-in `.env`. **Verify this by copying the repo (git-tracked files only) to a temp folder and running it.**
- README: 3-minute quickstart, configuration table, dashboard guide, suite table (what each proves + duration),
  repo map, troubleshooting table, security notes. `docs/TESTING_GUIDE.md`: mental model, account topology, how to read a
  report, severities, safety model, **how to add a suite in 4 steps**, known platform findings.
- Keep `conversation_history.txt`/handoff notes updated for the next AI agent but **never write secrets into it**.

## 7. Verification you must do (and show me evidence of)

1. `python -m pytest` passes offline (registry points at real files, every registry flag is accepted by its runner,
   command building rejects injection/junk, fixed instance can't be overridden, 412/400/403/401 guards, no secrets in
   `/api/config`, doctor flags placeholder credentials, every runner module imports).
2. Start the dashboard and drive it with Playwright: no JS console errors, every tab renders, the confirm modal works,
   no horizontal overflow at 390px wide. Take screenshots and look at them.
3. Launch one real suite from the dashboard via the API and confirm the history entry, archived log and exit status.
4. Run every suite on paper at a small size, then at full size. **For anything that fails, tell me what failed, the
   evidence, and whether it is a platform bug or a test problem (investigate before claiming either).**
   Example of a mistake to avoid: a "pending order never filled" failure that turned out to be the test waiting only
   14s in a quiet market - diagnose with a price tape before blaming the platform.
5. Report bugs found with exact request/response, and update the "known platform findings" section.

## 8. Lessons learned from the copy-trading build (apply them)

- Discover real field names from live responses; do not guess (I once read `qty` when the API used `net_qty`, and
  `status` when it used `state`, which made tests pass vacuously). Add assertions that a test actually checked something.
- Tests that pass trivially are worse than failing tests: print what was compared and the numbers.
- Pending/stop orders in quiet markets need adaptive waits; record whether the price crossed the trigger.
- A retrying HTTP client can duplicate non-idempotent POSTs - disable POST retries on 5xx.
- `GET /orders`-style endpoints may be unpaginated and grow forever - note it.
- Don't put the whole test run's evidence into git without checking for tokens; keep `reports/logs/` out of git.
- pytest must only collect `tests/` (live runners contain `test_*` functions that trade).
- Provide a seeded, reproducible random test; print the seed and op log on failure.
- Restore everything you change (balances, multipliers, memberships) even when a scenario crashes.

## 9. Working style

Work phase by phase (Discovery -> plan -> client + doctor + config -> runners -> dashboard backend -> UI -> tests/CI/docs ->
full verification). After each phase say what you built and what you verified. Ask me only when blocked by a decision
that is mine to make (credentials, business rules you cannot verify). Do not commit to git unless I ask. Be honest about
failures: report what failed, with evidence, and do not hide or soften it.
