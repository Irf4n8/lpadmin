# Bug-Inducing QA Scenario Report: BTC09 - Sub-Lot Micro Multiplier with Odd Decimals (0.75x Multiplier on 1.33 Lots)

**Execution Timestamp**: `2026-11-12T10:21:56.940814+00:00`  
**Scenario Outcome**: `✅ HANDLED CLEANLY`  
**Target Bug Category**: `Sub-Lot Decimal Precision & Truncation Boundary Bug`  
**Execution Duration**: `39.44s`  
**Exit Rule**: `Bracket Attached`

---
## Scenario Specifications & Real-World User Workflow
- **User Story**: Tests fractional product calculation (1.33 * 0.75 = 0.9975 lots) sitting 0.0025 below broker 1.00 min lot to test truncation vs rejection.
- **Symbol**: `BINANCE:BTCUSDT.P` | **Side**: `BUY` | **Master Lot**: `1.33`
- **Master Entry Price**: `$73,526.58` | **TP**: `73551.58` | **SL**: `73501.58`

---
## Replication & Execution Telemetry
| Metric | Observed Value | Expected Behavior |
| :--- | :--- | :--- |
| **Replication Rate** | `100.0%` (100/100) | 100% Replication |
| **Lot Sizing Match Rate** | `100.0%` | Sizing Formula Precision |
| **Residual Open Trades After Square-off** | `0` | `0` (Zero Orphan Trades) |

---
## Identified Bugs, Vulnerabilities & System Anomalies
- **No bugs observed.** The system handled this edge case gracefully without desynchronization, orphan positions, or calculation errors.
