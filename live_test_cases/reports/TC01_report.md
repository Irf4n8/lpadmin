# BlackTrader MAM QA Report: TC01 - Market BUY with TP Alone (+30 pts)

**Execution Timestamp**: `2026-11-12T07:18:57.534067+00:00`  
**Target Instrument**: `BINANCE:BTCUSDT.P`  
**Order Side**: `BUY`  
**Master Lot**: `1.25`  
**Expected Follower Lot (2.0x)**: `2.50`  
**Actual Detected Lot**: `2.50`  
**Exit Setting Attached?**: `YES (Bracket)`  
**Total Duration**: `48.19s`  
**Test Verdict**: **🟢 PASS (Zero Bugs Detected)**

---
## Execution & Price Verification

| Metric | Value | Status |
|:---|:---|:---:|
| **Live Market Price at Entry** | `$73,498.80` | Live Tick |
| **Master Fill Price** | `$73,498.80` | Confirmed |
| **Follower Sample Fill Price** | `$73,498.80` | Confirmed |
| **Execution Slippage** | `+0.00 pts` | ✅ Optimal |
| **Follower Replication Rate** | `100.0%` (100/100) | ✅ 100% |
| **Lot Sizing Fidelity** | `100.0%` (100/100) | ✅ 100% |
| **Residual Open Trades After Square-off** | `0` | ✅ Clean (0) |

---
## Bugs & Anomalies Identified
- **No bugs identified.** Exact replication, proper multiplier scaling, zero slippage anomalies, and synchronized square-off confirmed.
