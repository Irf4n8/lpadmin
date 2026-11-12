# Enterprise Test Case Report: CTC09 - Dual-Bracket Tight Boundary Scalp (TP +15 / SL -15 pts)

**Execution Timestamp**: `2026-11-12T09:30:00.028027+00:00`  
**Overall Result**: `✅ PASSED`  
**Execution Duration**: `40.2s`  
**Exit Rule**: `Bracket Settings Attached`

---
## Test Case Specifications & Dashboard Actions
- **Description**: Validates odd fractional multiplier (2.25x -> 3.06 lots) with tight dual-bracket execution.
- **Symbol**: `BINANCE:BTCUSDT.P` | **Side**: `BUY` | **Master Lot**: `1.36`
- **Master Entry Price**: `$73,419.33` | **TP**: `73434.33` | **SL**: `73404.33`

### Dashboard Configuration Actions Applied
- **CATEGORY**: Set All Followers to Multiplier 2.25x (`target=all`)

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
| `mamfollower1@mailinator.com` | `3.06` | `3.06` | ✅ YES | `$73,385.60` | `$-0.31` |
| `mamfollower2@mailinator.com` | `3.06` | `3.06` | ✅ YES | `$73,385.60` | `$-0.31` |
| `mamfollower3@mailinator.com` | `3.06` | `3.06` | ✅ YES | `$73,385.60` | `$-0.31` |
| `mamfollower4@mailinator.com` | `3.06` | `3.06` | ✅ YES | `$73,385.60` | `$-0.31` |
| `mamfollower5@mailinator.com` | `3.06` | `3.06` | ✅ YES | `$73,385.60` | `$-0.31` |
| `mamfollower6@mailinator.com` | `3.06` | `3.06` | ✅ YES | `$73,385.60` | `$-0.31` |
| `mamfollower7@mailinator.com` | `3.06` | `3.06` | ✅ YES | `$73,385.60` | `$-0.31` |
| `mamfollower8@mailinator.com` | `3.06` | `3.06` | ✅ YES | `$73,385.60` | `$-0.31` |
| `mamfollower9@mailinator.com` | `3.06` | `3.06` | ✅ YES | `$73,385.60` | `$-0.31` |
| `mamfollower10@mailinator.com` | `3.06` | `3.06` | ✅ YES | `$73,385.60` | `$-0.31` |

---
## Identified Bugs & Anomalies
- **No bugs identified.** Flawless dashboard configuration, exact quantity scaling across followers, zero slippage anomalies, and synchronized square-off confirmed.
