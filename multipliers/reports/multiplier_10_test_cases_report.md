# BlackTrader MAM: Multiplier Category (2.0x) QA Report

**Execution Timestamp**: `2026-11-12T06:58:13.916117+00:00`  
**Fixed Symbol Tested**: `BINANCE:BTCUSDT.P`  
**Sizing Category**: `Multiplier (2.0x)`  
**Total Follower Accounts**: `100`  
**Suite Duration**: `130.67s`  
**Final Verdict**: **🟢 ALL 10 PASSED (100% PASS)**

---
## Production Test Matrix Execution Results

| TC ID | Scenario Description | Side | Master Lot | Expected Follower Lot | Actual Detected Lot | Replication Rate | Sizing Match | Clean Exit | Status |
|:---:|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **TC01** | Market BUY with TP Alone (+30 pts) | `BUY` | `1.25` | `2.50` | `2.50` | `100.0%` | `100.0%` | ✅ 0 Residual | ✅ PASS |
| **TC02** | Market BUY with SL Alone (-25 pts) | `BUY` | `1.50` | `3.00` | `3.00` | `100.0%` | `100.0%` | ✅ 0 Residual | ✅ PASS |
| **TC03** | Market BUY with Both TP & SL (+25 / -25 pts) | `BUY` | `1.35` | `2.70` | `2.70` | `100.0%` | `100.0%` | ✅ 0 Residual | ✅ PASS |
| **TC04** | Market BUY with No TP/SL (Manual Timed Square-off) | `BUY` | `1.75` | `3.50` | `3.50` | `100.0%` | `100.0%` | ✅ 0 Residual | ✅ PASS |
| **TC05** | Market SELL with TP Alone (-30 pts) | `SELL` | `1.20` | `2.40` | `2.40` | `100.0%` | `100.0%` | ✅ 0 Residual | ✅ PASS |
| **TC06** | Market SELL with SL Alone (+25 pts) | `SELL` | `1.45` | `2.90` | `2.90` | `100.0%` | `100.0%` | ✅ 0 Residual | ✅ PASS |
| **TC07** | Market SELL with Both TP & SL (-25 / +25 pts) | `SELL` | `1.60` | `3.20` | `3.20` | `100.0%` | `100.0%` | ✅ 0 Residual | ✅ PASS |
| **TC08** | Market SELL with No TP/SL (Manual Timed Square-off) | `SELL` | `1.80` | `3.60` | `3.60` | `100.0%` | `100.0%` | ✅ 0 Residual | ✅ PASS |
| **TC09** | Odd Fractional Decimal Precision (1.37 Lots) | `BUY` | `1.37` | `2.74` | `2.74` | `100.0%` | `100.0%` | ✅ 0 Residual | ✅ PASS |
| **TC10** | Multi-Leg Concurrent Pyramid Execution (Leg A + Leg B) | `BUY` | `2.50` | `5.00` | `5.00` | `100.0%` | `100.0%` | ✅ 0 Residual | ✅ PASS |

---
## Technical Key Findings
1. **Strict Production Multiplier Multi-Account Sizing**: Every follower account dynamically scaled by exactly 2.0x.
2. **Zero Sub-1 Lot Rule Compliance**: All test scenarios strictly utilized lots >= 1.0 with realistic decimal precision (1.25, 1.50, 1.35, 1.75, 1.37, 2.50).
3. **Fixed Production Instrument**: All tests were executed on `BINANCE:BTCUSDT.P`.
4. **Synchronized Square-off**: Master position square-off reliably triggered automated, mirrored closures across all 100 followers with 0 residual open trades.
