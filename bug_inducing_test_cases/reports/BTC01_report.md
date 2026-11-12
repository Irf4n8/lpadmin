# Bug-Inducing QA Scenario Report: BTC01 - Fractional Sub-Lot Floor Rounding Trap (0.25x vs Broker Min Lot 1.0)

**Execution Timestamp**: `2026-11-12T10:12:37.846664+00:00`  
**Scenario Outcome**: `✅ HANDLED CLEANLY`  
**Target Bug Category**: `Risk Management & Sub-Lot Rounding Anomaly`  
**Execution Duration**: `39.34s`  
**Exit Rule**: `Bracket Attached`

---
## Scenario Specifications & Real-World User Workflow
- **User Story**: User sets multiplier to 0.25x intending 25% risk, but broker enforces minimum lot 1.0, testing if follower risk is quadrupled unexpectedly.
- **Symbol**: `BINANCE:BTCUSDT.P` | **Side**: `BUY` | **Master Lot**: `1.0`
- **Master Entry Price**: `$73,427.54` | **TP**: `73452.54` | **SL**: `73402.54`

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
