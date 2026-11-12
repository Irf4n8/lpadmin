# Bug-Inducing QA Scenario Report: BTC05 - Inverted / Crossed Bracket Order Entry (Fat-Finger Bracket Validation)

**Execution Timestamp**: `2026-11-12T10:43:06.799511+00:00`  
**Scenario Outcome**: `🚨 BUG IDENTIFIED`  
**Target Bug Category**: `Order Validation Bypass & Corrupted Bracket Propagation`  
**Execution Duration**: `61.44s`  
**Exit Rule**: `Bracket Attached`

---
## Scenario Specifications & Real-World User Workflow
- **User Story**: User enters BUY order with inverted Stop-Loss higher than market price; tests if OMS rejects safely or propagates corrupted order to fleet.
- **Symbol**: `BINANCE:BTCUSDT.P` | **Side**: `BUY` | **Master Lot**: `1.2`
- **Master Entry Price**: `$73,500.54` | **TP**: `73450.54` | **SL**: `73550.54`

---
## Replication & Execution Telemetry
| Metric | Observed Value | Expected Behavior |
| :--- | :--- | :--- |
| **Replication Rate** | `100.0%` (100/100) | 100% Replication |
| **Lot Sizing Match Rate** | `100.0%` | Sizing Formula Precision |
| **Residual Open Trades After Square-off** | `0` | `0` (Zero Orphan Trades) |

---
## Identified Bugs, Vulnerabilities & System Anomalies
### ⚠️ [CRITICAL ARCHITECTURAL FINDING] Frontend vs. Backend Validation Discrepancy
> **Observation**:
> 1. **Web UI Terminal (Platform Frontend)**: As verified in live manual testing, the trading interface contains client-side validation:
>    `"Stop loss must be below and take profit above the bid (...) — a buy closes at the bid."`
>    The UI successfully blocks manual human fat-finger mistakes directly in the modal.
> 2. **Backend OMS REST API (`POST /v1/oms/paper/orders`)**: When an order with inverted TP/SL is sent directly via API/algo/webhook, the backend OMS accepted and filled the order without server-side validation.
>
> **Takeaway & Recommendation**: The client-side UI validation is working as designed. However, server-side validation should be added to the OMS backend endpoint to guarantee that API/algorithmic integrations cannot bypass the check.

