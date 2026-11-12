# Bug-Inducing QA Scenario Report: BTC04 - Extreme Micro-Capital Asymmetry in Balance Mode ($50 vs $10M)

**Execution Timestamp**: `2026-11-12T10:16:49.815930+00:00`  
**Scenario Outcome**: `✅ HANDLED CLEANLY`  
**Target Bug Category**: `Proportional Divide-By-Zero / Margin Squeeze`  
**Execution Duration**: `43.59s`  
**Exit Rule**: `Bracket Attached`

---
## Scenario Specifications & Real-World User Workflow
- **User Story**: Tests Balance-Based sizing calculation on $50 account (expected 0.00001 lots) to verify if OMS rounds up causing instant liquidation.
- **Symbol**: `BINANCE:BTCUSDT.P` | **Side**: `BUY` | **Master Lot**: `2.0`
- **Master Entry Price**: `$73,433.08` | **TP**: `73458.08` | **SL**: `73408.08`

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
