# Breakpoint & Race-Condition Hunter Report

**Generated:** 2026-11-18T10:11:20.089378+00:00  
**Instance:** `real` | **Followers:** 10 | **Master:** `master2@mailinator.com`

| Scenario | Result | Findings |
| :--- | :---: | :--- |
| B1 Duplicate squareoff storm | ❌ FAIL | 1 HIGH, 0 MED |
| B2 Over-reduce race | ❌ FAIL | 1 HIGH, 0 MED |
| B3 Protection write storm | ✅ PASS | 0 HIGH, 0 MED |
| B4 Double-cancel storm | ✅ PASS | 0 HIGH, 0 MED |
| B5 Load ramp (breaking point) | ❌ FAIL | 1 HIGH, 1 MED |
| B6 Follow/unfollow flapping | ✅ PASS | 0 HIGH, 0 MED |
| B7 Margin exhaustion | ✅ PASS | 0 HIGH, 0 MED |
| B8 Input fuzz | ❌ FAIL | 1 HIGH, 0 MED |
| B9 Bulk vs individual close | ✅ PASS | 0 HIGH, 0 MED |
| B10 Auth/token refresh storm | ✅ PASS | 0 HIGH, 0 MED |
| B11 Final consistency audit | ✅ PASS | 0 HIGH, 0 MED |

## Findings

### B1 Duplicate squareoff storm
- **HIGH** — follower did not receive copied position - cannot run scenario

### B2 Over-reduce race
- **HIGH** — no follower position

### B5 Load ramp (breaking point)
- **HIGH** — @25 concurrent: 1 followers MISSING copies (149/150 positions) after 25s
- **MED** — @25 concurrent: non-200 responses {400: 10}
- **INFO** — first degradation at: 25 concurrent master orders

### B8 Input fuzz
- **HIGH** — 5xx on invalid input {"qty": 1, "side": "BUY", "symbol": "BINANCE:BTCUSDT.P", "type": "WEIRD"} -> 599 EXC RetryError: HTTPSConnectionPool(host='lpadmin.blackfx.com', port=443): Max r

## Load ramp

| Threads | Placed | p50 s | p95 s | Fan-out lag s | Short | Dup | Positions |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| 10 | 10 | 0.133 | 0.168 | 0.4 | 0 | 0 | 100/100 |
| 25 | 15 | 0.434 | 0.971 | 25.23 | 1 | 0 | 149/150 |
