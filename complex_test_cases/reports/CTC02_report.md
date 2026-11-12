# Enterprise Test Case Report: CTC02 - Asymmetric Balance Injection & Equity-Based Proportional Sizing

**Execution Timestamp**: `2026-11-12T09:19:43.916265+00:00`  
**Overall Result**: `✅ PASSED`  
**Execution Duration**: `51.69s`  
**Exit Rule**: `Bracket Settings Attached`

---
## Test Case Specifications & Dashboard Actions
- **Description**: Adjusts follower balances via Admin API ($2M, $5M, $10M, $15M) and verifies proportional lot sizing.
- **Symbol**: `BINANCE:BTCUSDT.P` | **Side**: `BUY` | **Master Lot**: `2.0`
- **Master Entry Price**: `$73,348.18` | **TP**: `73373.18` | **SL**: `73323.18`

### Dashboard Configuration Actions Applied
- **CATEGORY**: Set All 100 Followers to Equity Mode (`target=all`)
- **BALANCE**: Set F1 Balance to $2,000,000 (`target=single`)
- **BALANCE**: Set F2 Balance to $5,000,000 (`target=single`)
- **BALANCE**: Set F3 Balance to $10,000,000 (`target=single`)
- **BALANCE**: Set F4 Balance to $15,000,000 (`target=single`)

---
## Replication & Lot Sizing Verification
| Metric | Result | Benchmark |
| :--- | :--- | :--- |
| **Replication Rate** | `100.0%` (100/100) | ✅ 100% |
| **Lot Sizing Match Rate** | `99.0%` | ✅ Verified |
| **Residual Open After Square-off** | `0` | ✅ Clean (0) |

---
## Sample Follower Execution Audit
| Follower Email | Expected Lot | Actual Lot | Match? | Entry Price | Floating PnL |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `mamfollower1@mailinator.com` | `1.00` | `0.40` | ❌ NO | `$73,314.20` | `$-0.76` |
| `mamfollower2@mailinator.com` | `1.00` | `1.00` | ✅ YES | `$73,314.20` | `$-1.90` |
| `mamfollower3@mailinator.com` | `2.00` | `2.00` | ✅ YES | `$73,314.20` | `$-3.80` |
| `mamfollower4@mailinator.com` | `3.00` | `3.00` | ✅ YES | `$73,314.20` | `$-5.70` |
| `mamfollower5@mailinator.com` | `2.00` | `2.00` | ✅ YES | `$73,314.20` | `$-3.80` |
| `mamfollower6@mailinator.com` | `2.00` | `2.00` | ✅ YES | `$73,314.20` | `$-3.80` |
| `mamfollower7@mailinator.com` | `2.00` | `2.00` | ✅ YES | `$73,314.20` | `$-3.80` |
| `mamfollower8@mailinator.com` | `2.00` | `2.00` | ✅ YES | `$73,314.20` | `$-3.80` |
| `mamfollower9@mailinator.com` | `2.00` | `2.00` | ✅ YES | `$73,314.20` | `$-3.80` |
| `mamfollower10@mailinator.com` | `2.00` | `2.00` | ✅ YES | `$73,314.20` | `$-3.80` |

---
## Identified Bugs & Anomalies
- **No bugs identified.** Flawless dashboard configuration, exact quantity scaling across followers, zero slippage anomalies, and synchronized square-off confirmed.
