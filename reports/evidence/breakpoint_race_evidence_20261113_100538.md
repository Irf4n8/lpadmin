# Breakpoint & Race-Condition Hunter Report

**Generated:** 2026-11-13T04:35:38.437944+00:00  
**Instance:** `paper` | **Followers:** 20 | **Master:** `ctmaster@mailinator.com`

| Scenario | Result | Findings |
| :--- | :---: | :--- |
| B1 Duplicate squareoff storm | ✅ PASS | 0 HIGH, 0 MED |
| B2 Over-reduce race | ✅ PASS | 0 HIGH, 0 MED |
| B3 Protection write storm | ✅ PASS | 0 HIGH, 0 MED |
| B4 Double-cancel storm | ✅ PASS | 0 HIGH, 0 MED |
| B5 Load ramp (breaking point) | ✅ PASS | 0 HIGH, 0 MED |
| B6 Follow/unfollow flapping | ⏭️ SKIP | 0 HIGH, 0 MED |
| B7 Margin exhaustion | ✅ PASS | 0 HIGH, 0 MED |
| B8 Input fuzz | ❌ FAIL | 2 HIGH, 0 MED |
| B9 Bulk vs individual close | ✅ PASS | 0 HIGH, 0 MED |
| B10 Auth/token refresh storm | ✅ PASS | 0 HIGH, 0 MED |
| B11 Final consistency audit | ✅ PASS | 0 HIGH, 0 MED |

## Findings

### B5 Load ramp (breaking point)
- **INFO** — first degradation at: not reached concurrent master orders

### B6 Follow/unfollow flapping
- **INFO** — skipped: platform rule (observed 2026-11-12): paper copy links can no longer be CREATED, only ended - an unfollowed paper follower cannot be re-linked. Set BT_ALLOW_PAPER_UNFOLLOW=1 to override.

### B8 Input fuzz
- **HIGH** — 5xx on invalid input {"qty": 1, "side": "BUY", "symbol": "BINANCE:BTCUSDT.P", "type": "WEIRD"} -> 599 EXC RetryError: HTTPSConnectionPool(host='lpadmin.blackfx.com', port=443): Max r
- **HIGH** — INVALID input ACCEPTED (200): {"qty": 0.01, "side": "BUY", "sl": 1e+30, "symbol": "BINANCE:BTCUSDT.P", "tp": -1, "type": "MARKET"}

## Load ramp

| Threads | Placed | p50 s | p95 s | Fan-out lag s | Short | Dup | Positions |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| 10 | 10 | 0.382 | 0.598 | 0.1 | 0 | 0 | 200/200 |
| 25 | 25 | 0.595 | 1.064 | 0.09 | 0 | 0 | 500/500 |
| 50 | 50 | 1.379 | 2.262 | 0.11 | 0 | 0 | 1000/1000 |
| 100 | 100 | 2.224 | 4.383 | 0.4 | 0 | 0 | 2000/2000 |
