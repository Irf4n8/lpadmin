# BlackTrader OMS - Paper Trading 2x Multiplier Certification Report

- **Execution Timestamp**: 2026-11-12 11:19:52 UTC
- **Broker Instance**: `PAPER` (Simulation Mode)
- **Configured Multiplier**: `2.0x`
- **Master Order Size**: `10.0 Lot`
- **Expected Follower Size**: `20.0 Lot` (2.0x Multiplier)
- **Target Capital**: $100,000,000.00 Equalized across all 101 Accounts
- **Total Followers Tested**: 100
- **Overall Suite Status**: **PASSED (100%)**
- **Total Duration**: 45.03 seconds

## Phase Breakdown & Multiplier Verification

| # | Phase / Test | Status | Key Metric / Verification |
|---|---|---|---|
| 1 | Balance Synchronization (Paper) | **PASS** | `{"target_balance": 100000000.0, "success_count": 101, "total_accounts": 101, "duration_sec": 1.22}` |
| 2 | Follow Link Configuration (2.0x Multiplier on Paper) | **PASS** | `{"valid_2x_followers": 100, "total_followers": 100, "target_multiplier": 2.0, "duration_sec": 10.36}` |
| 3 | Order 1 (10.0 Lot BUY -> 20.0 Lot Follower) | **PASS** | `{"master_lot": 10.0, "expected_follower_lot": 20.0, "symbol": "BINANCE:BTCUSDT.P", "side": "BUY", "followers_copied": 100, "total_followers": 100, "replication_rate_pct": 100.0}` |
| 4 | Order 2 (10.0 Lot SELL -> 20.0 Lot Follower) | **PASS** | `{"master_lot": 10.0, "expected_follower_lot": 20.0, "symbol": "BINANCE:BTCUSDT.P", "side": "SELL", "followers_copied": 100, "total_followers": 100, "replication_rate_pct": 100.0}` |
