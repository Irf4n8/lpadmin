# Bug-Inducing QA Scenario Report: BTC02 - Dangling Orphan Position via Mid-Trade Unfollow ('Leave Manager' Mid-Flight)

**Execution Timestamp**: `2026-11-12T10:28:17.312964+00:00`  
**Scenario Outcome**: `✅ HANDLED CLEANLY`  
**Target Bug Category**: `Dangling Orphan Position & State Desync`  
**Execution Duration**: `155.78s`  
**Exit Rule**: `120-Second Mandatory Live Countdown`

---
## Scenario Specifications & Real-World User Workflow
- **User Story**: Follower clicks 'Leave Manager' while holding an open position; tests if position is orphaned or master square-off fails.
- **Symbol**: `BINANCE:BTCUSDT.P` | **Side**: `BUY` | **Master Lot**: `1.5`
- **Master Entry Price**: `$73,599.65` | **TP**: `None` | **SL**: `None`

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
