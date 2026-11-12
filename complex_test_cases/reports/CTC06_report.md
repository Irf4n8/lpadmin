# Enterprise Test Case Report: CTC06 - High-Volume Stress Sizing (Master 3.50 Lots -> 700 Follower Lots Pool)

**Execution Timestamp**: `2026-11-12T09:25:13.954006+00:00`  
**Overall Result**: `✅ PASSED`  
**Execution Duration**: `36.31s`  
**Exit Rule**: `Bracket Settings Attached`

---
## Test Case Specifications & Dashboard Actions
- **Description**: Heavy lot replication test generating 700+ lots across 100 followers to verify OMS throughput.
- **Symbol**: `BINANCE:BTCUSDT.P` | **Side**: `SELL` | **Master Lot**: `3.5`
- **Master Entry Price**: `$73,350.64` | **TP**: `73325.64` | **SL**: `73375.64`

### Dashboard Configuration Actions Applied
- **CATEGORY**: Ensure All Followers at Multiplier 2.0x (`target=all`)

---
## Replication & Lot Sizing Verification
| Metric | Result | Benchmark |
| :--- | :--- | :--- |
| **Replication Rate** | `100.0%` (100/100) | ✅ 100% |
| **Lot Sizing Match Rate** | `100.0%` | ✅ Verified |
| **Residual Open After Square-off** | `0` | ✅ Clean (0) |

---
## Sample Follower Execution Audit
| Follower Email | Expected Lot | Actual Lot | Match? | Entry Price | Floating PnL |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `mamfollower1@mailinator.com` | `7.00` | `7.00` | ✅ YES | `$73,318.40` | `$-0.70` |
| `mamfollower2@mailinator.com` | `7.00` | `7.00` | ✅ YES | `$73,318.40` | `$-0.70` |
| `mamfollower3@mailinator.com` | `7.00` | `7.00` | ✅ YES | `$73,318.40` | `$-0.70` |
| `mamfollower4@mailinator.com` | `7.00` | `7.00` | ✅ YES | `$73,318.40` | `$-0.70` |
| `mamfollower5@mailinator.com` | `7.00` | `7.00` | ✅ YES | `$73,318.40` | `$-0.70` |
| `mamfollower6@mailinator.com` | `7.00` | `7.00` | ✅ YES | `$73,318.40` | `$-0.70` |
| `mamfollower7@mailinator.com` | `7.00` | `7.00` | ✅ YES | `$73,318.40` | `$-0.70` |
| `mamfollower8@mailinator.com` | `7.00` | `7.00` | ✅ YES | `$73,318.40` | `$-0.70` |
| `mamfollower9@mailinator.com` | `7.00` | `7.00` | ✅ YES | `$73,318.40` | `$-0.70` |
| `mamfollower10@mailinator.com` | `7.00` | `7.00` | ✅ YES | `$73,318.40` | `$-0.70` |

---
## Identified Bugs & Anomalies
- **No bugs identified.** Flawless dashboard configuration, exact quantity scaling across followers, zero slippage anomalies, and synchronized square-off confirmed.
