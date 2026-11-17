# BlackTrader OMS - Real Money Copy Trading Certification Report

- **Execution Timestamp**: 2026-11-17 04:38:32 UTC
- **Broker Instance**: `REAL` (Live Money Mode)
- **Target Capital**: $100,000,000.00 Equalized across all 101 Accounts
- **Total Followers**: 100
- **Overall Suite Status**: **PARTIAL**
- **Total Duration**: 53.25 seconds

## Phase & Order Breakdown

| # | Phase / Order | Status | Key Metric / Verification |
|---|---|---|---|
| 1 | Balance Synchronization | **PASS** | {"target_balance": 100000000.0, "success_count": 101, "total_accounts": 101, "duration_sec": 0.71} |
| 2 | Copy Link Migration to REAL | **PASS** | {"real_active_followers": 100, "total_followers": 100, "duration_sec": 3.84} |
| 3 | Order 1 (BUY MARKET on REAL) | **PASS** | {"master_lot": 0.05, "symbol": "BINANCE:BTCUSDT.P", "side": "BUY", "followers_copied": 100, "total_followers": 100, "replication_rate_pct": 100.0} |
| 4 | Order 2 (SELL MARKET on REAL) | **FAIL** | {"master_lot": 0.05, "symbol": "BINANCE:BTCUSDT.P", "side": "SELL", "followers_copied": 79, "total_followers": 100, "replication_rate_pct": 79.0} |
| 5 | Order 3 (BUY with TP/SL on REAL) | **PASS** | {"master_lot": 0.1, "symbol": "BINANCE:BTCUSDT.P", "tp_price": 65234.0, "sl_price": 64734.0, "followers_copied": 100, "total_followers": 100, "replication_rate_pct": 100.0} |
