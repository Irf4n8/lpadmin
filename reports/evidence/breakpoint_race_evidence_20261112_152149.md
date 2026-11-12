# Breakpoint & Race-Condition Hunter Report

**Generated:** 2026-11-12T09:51:49.162597+00:00  
**Instance:** `paper` | **Followers:** 20 | **Master:** `ctmaster@mailinator.com`

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
| 10 | 10 | 0.498 | 0.69 | 0.35 | 0 | 0 | 200/200 |
| 25 | 25 | 0.96 | 1.555 | 0.12 | 0 | 0 | 500/500 |
| 50 | 50 | 1.562 | 2.83 | 0.13 | 0 | 0 | 1000/1000 |
