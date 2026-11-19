# BlackTrader OMS - Pending Trigger & Modification Race Audit Report

- **Execution Timestamp**: 2026-11-18 10:06:56 UTC
- **Total Scenarios Tested**: 3
- **Passed Scenarios**: 2 / 3
- **Overall Suite Status**: PARTIAL
- **Total Duration**: 66.50 seconds

## Scenario Breakdown

| # | Scenario Name | Status | Key Metric / Verification |
|---|---|---|---|
| 1 | Cancel-at-Trigger Millisecond Collision | **FAIL** | {"order_id": "ord_aabe395012361fc1dd", "master_final_state": "FILLED", "master_has_position": true, "followers_with_position": 0, "split_brain_detected": false, "race_winner": "EXECUTION"} |
| 2 | Trigger Protection Modification | **PASS** | {"note": "Market tick did not cross in window"} |
| 3 | Multi-Threaded Pending Trigger Storm | **PASS** | {"num_orders": 5, "storm_time_ms": 804.28, "post_cleanup_master_positions": 0} |
