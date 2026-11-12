# Breakpoint & Race-Condition Hunter Report

**Generated:** 2026-11-12T11:25:14.772472+00:00  
**Instance:** `paper` | **Followers:** 100 | **Master:** `ctmaster@mailinator.com`

| Scenario | Result | Findings |
| :--- | :---: | :--- |
| B1 Duplicate squareoff storm | ✅ PASS | 0 HIGH, 0 MED |
| B2 Over-reduce race | ✅ PASS | 0 HIGH, 0 MED |
| B3 Protection write storm | ✅ PASS | 0 HIGH, 0 MED |
| B4 Double-cancel storm | ✅ PASS | 0 HIGH, 0 MED |
| B5 Load ramp (breaking point) | ✅ PASS | 0 HIGH, 0 MED |
| B6 Follow/unfollow flapping | ✅ PASS | 0 HIGH, 0 MED |
| B7 Margin exhaustion | ✅ PASS | 0 HIGH, 0 MED |
| B8 Input fuzz | ❌ FAIL | 2 HIGH, 0 MED |
| B9 Bulk vs individual close | ✅ PASS | 0 HIGH, 0 MED |
| B10 Auth/token refresh storm | ✅ PASS | 0 HIGH, 0 MED |
| B11 Final consistency audit | ✅ PASS | 0 HIGH, 0 MED |

## Findings

### B5 Load ramp (breaking point)
- **INFO** — first degradation at: not reached concurrent master orders

### B8 Input fuzz
- **HIGH** — 5xx on invalid input {"qty": 1, "side": "BUY", "symbol": "BINANCE:BTCUSDT.P", "type": "WEIRD"} -> 599 EXC RetryError: HTTPSConnectionPool(host='lpadmin.blackfx.com', port=443): Max r
- **HIGH** — INVALID input ACCEPTED (200): {"qty": 0.01, "side": "BUY", "sl": 1e+30, "symbol": "BINANCE:BTCUSDT.P", "tp": -1, "type": "MARKET"}

## Load ramp

| Threads | Placed | p50 s | p95 s | Fan-out lag s | Short | Dup | Positions |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| 10 | 10 | 0.366 | 0.533 | 0.23 | 0 | 0 | 1000/1000 |
| 25 | 25 | 0.583 | 0.923 | 0.26 | 0 | 0 | 2500/2500 |
| 50 | 50 | 1.001 | 1.81 | 0.3 | 0 | 0 | 5000/5000 |
| 100 | 100 | 1.93 | 3.7 | 0.3 | 0 | 0 | 10000/10000 |
