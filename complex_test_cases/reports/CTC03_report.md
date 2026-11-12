# Enterprise Test Case Report: CTC03 - Balance-Based Proportional Sizing with Multi-Step Balances

**Execution Timestamp**: `2026-11-12T09:20:45.599470+00:00`  
**Overall Result**: `✅ PASSED`  
**Execution Duration**: `47.99s`  
**Exit Rule**: `Bracket Settings Attached`

---
## Test Case Specifications & Dashboard Actions
- **Description**: Sets followers to Balance-Based sizing with multi-tier capital allocation ($5M, $10M, $20M).
- **Symbol**: `BINANCE:BTCUSDT.P` | **Side**: `SELL` | **Master Lot**: `2.0`
- **Master Entry Price**: `$73,302.01` | **TP**: `None` | **SL**: `73332.01`

### Dashboard Configuration Actions Applied
- **CATEGORY**: Set All Followers to Balance Mode (`target=all`)
- **BALANCE**: Set F1-F10 Balance to $5,000,000 (`target=range`)
- **BALANCE**: Set F11-F20 Balance to $10,000,000 (`target=range`)
- **BALANCE**: Set F21-F30 Balance to $20,000,000 (`target=range`)

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
| `mamfollower1@mailinator.com` | `1.00` | `1.00` | ✅ YES | `$73,265.80` | `$+0.00` |
| `mamfollower2@mailinator.com` | `1.00` | `1.00` | ✅ YES | `$73,265.80` | `$+0.00` |
| `mamfollower3@mailinator.com` | `1.00` | `1.00` | ✅ YES | `$73,265.80` | `$+0.00` |
| `mamfollower4@mailinator.com` | `1.00` | `1.00` | ✅ YES | `$73,265.80` | `$+0.00` |
| `mamfollower5@mailinator.com` | `1.00` | `1.00` | ✅ YES | `$73,265.80` | `$+0.00` |
| `mamfollower6@mailinator.com` | `1.00` | `1.00` | ✅ YES | `$73,265.80` | `$+0.00` |
| `mamfollower7@mailinator.com` | `1.00` | `1.00` | ✅ YES | `$73,265.80` | `$+0.00` |
| `mamfollower8@mailinator.com` | `1.00` | `1.00` | ✅ YES | `$73,265.80` | `$+0.00` |
| `mamfollower9@mailinator.com` | `1.00` | `1.00` | ✅ YES | `$73,265.80` | `$+0.00` |
| `mamfollower10@mailinator.com` | `1.00` | `1.00` | ✅ YES | `$73,265.80` | `$+0.00` |

---
## Identified Bugs & Anomalies
- **No bugs identified.** Flawless dashboard configuration, exact quantity scaling across followers, zero slippage anomalies, and synchronized square-off confirmed.
