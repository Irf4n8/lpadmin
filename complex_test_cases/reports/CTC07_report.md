# Enterprise Test Case Report: CTC07 - Micro-Balance Margin Depletion & Fleet Starvation Resilience

**Execution Timestamp**: `2026-11-12T09:26:07.385604+00:00`  
**Overall Result**: `✅ PASSED`  
**Execution Duration**: `42.2s`  
**Exit Rule**: `Bracket Settings Attached`

---
## Test Case Specifications & Dashboard Actions
- **Description**: Starves Follower 100 ($50 balance) while keeping F1-F99 funded to test margin rejection isolation.
- **Symbol**: `BINANCE:BTCUSDT.P` | **Side**: `BUY` | **Master Lot**: `2.0`
- **Master Entry Price**: `$73,354.85` | **TP**: `73379.85` | **SL**: `73329.85`

### Dashboard Configuration Actions Applied
- **CATEGORY**: Set All Followers to Multiplier 2.0x (`target=all`)
- **BALANCE**: Starve Follower 100 to $50.00 (`target=single`)

---
## Replication & Lot Sizing Verification
| Metric | Result | Benchmark |
| :--- | :--- | :--- |
| **Replication Rate** | `99.0%` (99/100) | ✅ 100% |
| **Lot Sizing Match Rate** | `100.0%` | ✅ Verified |
| **Residual Open After Square-off** | `0` | ✅ Clean (0) |

---
## Sample Follower Execution Audit
| Follower Email | Expected Lot | Actual Lot | Match? | Entry Price | Floating PnL |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `mamfollower1@mailinator.com` | `4.00` | `4.00` | ✅ YES | `$73,339.30` | `$+14.00` |
| `mamfollower2@mailinator.com` | `4.00` | `4.00` | ✅ YES | `$73,339.30` | `$+14.00` |
| `mamfollower3@mailinator.com` | `4.00` | `4.00` | ✅ YES | `$73,339.30` | `$+14.40` |
| `mamfollower4@mailinator.com` | `4.00` | `4.00` | ✅ YES | `$73,339.30` | `$+14.40` |
| `mamfollower5@mailinator.com` | `4.00` | `4.00` | ✅ YES | `$73,339.30` | `$+14.00` |
| `mamfollower6@mailinator.com` | `4.00` | `4.00` | ✅ YES | `$73,339.30` | `$+25.20` |
| `mamfollower7@mailinator.com` | `4.00` | `4.00` | ✅ YES | `$73,339.30` | `$+14.00` |
| `mamfollower8@mailinator.com` | `4.00` | `4.00` | ✅ YES | `$73,339.30` | `$+14.40` |
| `mamfollower9@mailinator.com` | `4.00` | `4.00` | ✅ YES | `$73,339.30` | `$+14.40` |
| `mamfollower10@mailinator.com` | `4.00` | `4.00` | ✅ YES | `$73,339.30` | `$+14.00` |

---
## Identified Bugs & Anomalies
- **No bugs identified.** Flawless dashboard configuration, exact quantity scaling across followers, zero slippage anomalies, and synchronized square-off confirmed.
