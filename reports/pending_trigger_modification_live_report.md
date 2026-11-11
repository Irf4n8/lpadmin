# BlackTrader OMS - Live Pending Trigger Modification Race Report

- **Execution Timestamp**: 2026-11-11 13:03:35 UTC
- **Passed Scenarios**: 3 / 3
- **Overall Suite Status**: PASSED (100%)
- **Total Duration**: 60.26 seconds

## Scenario Breakdown

| # | Scenario Name | Status | Key Metric / Verification |
|---|---|---|---|
| 1 | BUY LIMIT Trigger Price Shift at Hit Boundary | **PASS** | {"mod_time_ms": 156.67, "ord1_state": "FILLED", "ord2_state": "PENDING", "master_positions": 1, "followers_with_pos": 100, "followers_with_duplicates": 0} |
| 2 | SELL LIMIT Trigger Price Shift at Hit Boundary | **PASS** | {"mod_time_ms": 111.4, "ord1_state": "FILLED", "ord2_state": "PENDING", "followers_with_pos": 100, "followers_with_duplicates": 0} |
| 3 | Impending Trigger TP/SL Protection Shift Collision | **PASS** | {"market_order_id": "ord_c6ca624557f5e71a16", "mod_time_ms": 193.74, "mod_status_code": 200, "followers_with_pos": 100} |
