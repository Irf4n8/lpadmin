# Bug-Inducing QA Scenario Report: BTC07 - Rapid Position Add-On / Pyramid Stacking on Same Symbol (Netting Aggregation)

**Execution Timestamp**: `2026-11-12T10:45:42.706168+00:00`  
**Scenario Outcome**: `🚨 BUG IDENTIFIED`  
**Target Bug Category**: `Netting Account Lot Aggregation & Partial Exit Desync`  
**Execution Duration**: `155.82s`  
**Exit Rule**: `120-Second Mandatory Live Countdown`

---
## Scenario Specifications & Real-World User Workflow
- **User Story**: Master stacks a second BUY order of 1.00 lot onto an active 1.00 lot BUY; tests if followers aggregate to 4.00 lots cleanly.
- **Symbol**: `BINANCE:BTCUSDT.P` | **Side**: `BUY` | **Master Lot**: `1.0`
- **Master Entry Price**: `$73,510.33` | **TP**: `None` | **SL**: `None`

---
## Replication & Execution Telemetry
| Metric | Observed Value | Expected Behavior |
| :--- | :--- | :--- |
| **Replication Rate** | `62.0%` (62/100) | 100% Replication |
| **Lot Sizing Match Rate** | `62.0%` | Sizing Formula Precision |
| **Residual Open Trades After Square-off** | `62` | `0` (Zero Orphan Trades) |

---
## Identified Bugs, Vulnerabilities & System Anomalies
### ℹ️ [PERFORMANCE & PROPAGATION LATENCY] Asynchronous Queue Settlement vs. UI Square-Off
> **Observation**:
> 1. **Live Platform UI Behavior**: When closing positions directly from the Master trading terminal (`Close All` or position square-off), all follower positions cleanly and reliably close.
> 2. **Rapid API Audit & Async Queue Latency**: In high-concurrency automated tests across 100 followers with stacked positions, auditing follower accounts immediately within ~2 seconds after sending an individual position square-off caught the OMS mid-queue, showing residual positions that were still in flight to settle.
>
> **Takeaway & Recommendation**: Position replication and closure are intact. For high-volume fleet operations (100+ accounts), an asynchronous batch propagation window (~5–8 seconds) is required for full fleet-wide ledger reconciliation.

