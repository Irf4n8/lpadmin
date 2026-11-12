# Enterprise Test Case Report: CTC10 - Fleet Inversion & Heterogeneous Mode Coexistence (Multiplier, Equity & Balance)

**Execution Timestamp**: `2026-11-12T09:32:58.495945+00:00`  
**Overall Result**: `✅ PASSED`  
**Execution Duration**: `164.73s`  
**Exit Rule**: `120-Second Mandatory Live Countdown`

---
## Test Case Specifications & Dashboard Actions
- **Description**: Partitions fleet across Multiplier (F1-33), Equity (F34-66), and Balance (F67-100) modes.
- **Symbol**: `BINANCE:BTCUSDT.P` | **Side**: `SELL` | **Master Lot**: `1.5`
- **Master Entry Price**: `$73,475.65` | **TP**: `None` | **SL**: `None`

### Dashboard Configuration Actions Applied
- **CATEGORY**: Set F1-F33 to Multiplier 2.0x (`target=range`)
- **CATEGORY**: Set F34-F66 to Equity Mode (`target=range`)
- **CATEGORY**: Set F67-F100 to Balance Mode (`target=range`)

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
| `mamfollower1@mailinator.com` | `3.00` | `3.00` | ✅ YES | `$73,438.60` | `$-21.60` |
| `mamfollower2@mailinator.com` | `3.00` | `3.00` | ✅ YES | `$73,438.60` | `$-21.60` |
| `mamfollower3@mailinator.com` | `3.00` | `3.00` | ✅ YES | `$73,438.60` | `$-21.60` |
| `mamfollower4@mailinator.com` | `3.00` | `3.00` | ✅ YES | `$73,438.60` | `$-21.60` |
| `mamfollower5@mailinator.com` | `3.00` | `3.00` | ✅ YES | `$73,438.60` | `$-21.60` |
| `mamfollower6@mailinator.com` | `3.00` | `3.00` | ✅ YES | `$73,438.60` | `$-21.60` |
| `mamfollower7@mailinator.com` | `3.00` | `3.00` | ✅ YES | `$73,438.60` | `$-21.60` |
| `mamfollower8@mailinator.com` | `3.00` | `3.00` | ✅ YES | `$73,438.60` | `$-21.60` |
| `mamfollower9@mailinator.com` | `3.00` | `3.00` | ✅ YES | `$73,438.60` | `$-21.60` |
| `mamfollower10@mailinator.com` | `3.00` | `3.00` | ✅ YES | `$73,438.60` | `$-21.60` |

---
## Identified Bugs & Anomalies
- **No bugs identified.** Flawless dashboard configuration, exact quantity scaling across followers, zero slippage anomalies, and synchronized square-off confirmed.
