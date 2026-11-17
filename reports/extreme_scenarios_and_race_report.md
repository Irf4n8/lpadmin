# BlackTrader OMS - Extreme Scenarios & Race Condition Audit Report

- **Execution Timestamp**: 2026-11-17 05:56:43 UTC
- **Total Scenarios Tested**: 7
- **Passed Scenarios**: 7 / 7
- **Overall Suite Status**: PASSED (100%)
- **Total Duration**: 146.85 seconds

## Scenario Breakdown

| # | Scenario Name | Status | Key Metric / Verification |
|---|---|---|---|
| 1 | Rapid Market Reversal (Long-to-Short Flip) | **PASS** | {"delta_ms": 234.95, "followers_with_orders": 100, "followers_with_pos": 100, "total_followers": 100} |
| 2 | Simultaneous Opposing Square-Offs (Row Locking) | **PASS** | {"collision_time_ms": 311.99, "collision_results_count": 6, "has_500_errors": false, "master_remaining_pos": 0, "follower_remaining_pos": 0} |
| 3 | Mid-Trade Dynamic Capital Shock | **PASS** | {"target_email": "follower10@mailinator.com", "entry_qty": 0.1, "initial_balance": 199999550.00042543, "shock_balance": 249999550.00042543, "final_open_positions": 0} |
| 4 | Micro-Lot Underflow (Sub-Contract Step) | **PASS** | {"master_qty": 0.001, "sample_tier4_lots": [0.002, 0.002, 0.002, 0.002, 0.002], "all_valid_lots": true} |
| 5 | Breakout Straddle & OCO Pending Cancellation | **PASS** | {"buy_stop_price": 65096.7, "sell_stop_price": 64496.7, "follower_hanging_pending": 0} |
| 6 | Cross-Asset Portfolio Bombardment | **PASS** | {"burst_time_ms": 187.68, "multi_asset_followers": 20, "sample_size": 20} |
| 7 | Full Accounting & Scaling Audit | **PASS** | {"master_lot": 0.05, "total_follower_volume": 9.625, "master_used_margin_post_cleanup": 0.0} |
