# Enterprise Test Case Report: CTC01 - Multi-Tier Multiplier Partitioning (F1-30: 1.5x, F31-70: 2.5x, F71-100: 3.0x)

**Execution Timestamp**: `2026-11-12T09:18:26.752822+00:00`  
**Overall Result**: `✅ PASSED`  
**Execution Duration**: `52.33s`  
**Exit Rule**: `Bracket Settings Attached`

---
## Test Case Specifications & Dashboard Actions
- **Description**: Validates partitioning the 100-follower fleet into 3 distinct multiplier tiers via dashboard API.
- **Symbol**: `BINANCE:BTCUSDT.P` | **Side**: `BUY` | **Master Lot**: `1.4`
- **Master Entry Price**: `$73,403.65` | **TP**: `73433.65` | **SL**: `73373.65`

### Dashboard Configuration Actions Applied
- **CATEGORY**: Set F1-F30 to Multiplier 1.5x (`target=range`)
- **CATEGORY**: Set F31-F70 to Multiplier 2.5x (`target=range`)
- **CATEGORY**: Set F71-F100 to Multiplier 3.0x (`target=range`)

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
| `mamfollower1@mailinator.com` | `2.10` | `2.10` | ✅ YES | `$73,370.70` | `$-0.21` |
| `mamfollower2@mailinator.com` | `2.10` | `2.10` | ✅ YES | `$73,370.70` | `$-0.21` |
| `mamfollower3@mailinator.com` | `2.10` | `2.10` | ✅ YES | `$73,370.70` | `$-0.21` |
| `mamfollower4@mailinator.com` | `2.10` | `2.10` | ✅ YES | `$73,370.70` | `$-0.21` |
| `mamfollower5@mailinator.com` | `2.10` | `2.10` | ✅ YES | `$73,370.70` | `$-0.21` |
| `mamfollower6@mailinator.com` | `2.10` | `2.10` | ✅ YES | `$73,370.70` | `$-0.21` |
| `mamfollower7@mailinator.com` | `2.10` | `2.10` | ✅ YES | `$73,370.70` | `$-0.21` |
| `mamfollower8@mailinator.com` | `2.10` | `2.10` | ✅ YES | `$73,370.70` | `$-0.21` |
| `mamfollower9@mailinator.com` | `2.10` | `2.10` | ✅ YES | `$73,370.70` | `$-0.21` |
| `mamfollower10@mailinator.com` | `2.10` | `2.10` | ✅ YES | `$73,370.70` | `$-0.21` |

---
## Identified Bugs & Anomalies
- **No bugs identified.** Flawless dashboard configuration, exact quantity scaling across followers, zero slippage anomalies, and synchronized square-off confirmed.
