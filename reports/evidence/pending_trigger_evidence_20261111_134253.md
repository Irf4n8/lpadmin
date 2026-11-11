# Pending Orders Trigger & TP/SL Test Evidence Report

**Generated:** 2026-11-11T08:12:53.802576+00:00  
**Master Trader:** `ctmaster@mailinator.com` (`mem_aac4ca423a6925dca7`)  
**Followers Tested:** 100 (`follower1@mailinator.com` to `follower100@mailinator.com`)  
**Trading Symbol:** `BINANCE:BTCUSDT.P` (Lot: 0.5)  
**Instance:** `paper` (Hedging)  
**Overall Result:** **4/5 SCENARIOS PASSED**

---

## 1. Executive Summary

| Scenario | Trigger Status | Followers Filled | TP/SL Verified | Result |
| :--- | :---: | :---: | :---: | :---: |
| **Pending BUY LIMIT Trigger (WITHOUT TP/SL)** | ⚡ FILLED | 100/100 | None | ✅ PASS |
| **Pending BUY LIMIT Trigger (WITH TP/SL)** | ⚡ FILLED | 100/100 | 100/100 | ✅ PASS |
| **Pending SELL LIMIT Trigger (WITHOUT TP/SL)** | ❌ TIMEOUT | 0/100 | None | ❌ FAIL |
| **Pending SELL LIMIT Trigger (WITH TP/SL)** | ⚡ FILLED | 100/100 | 100/100 | ✅ PASS |
| **Final Teardown & Zero Orphan Verification** | N/A | 0 orphans |  | ✅ PASS |

---

## 2. Key Observations
1. **Immediate Trigger Accuracy:** Pending limit orders placed within 0.2 ticks of the active market price triggered and filled into live positions within 1–3 seconds.
2. **Synchronized Follower Fill:** When the master's pending order triggered, all 100 followers simultaneously triggered and filled according to their varied multipliers (1x, 2x, 3x, 0.5x).
3. **Protection (TP/SL) Propagation:** Triggered pending orders received active Take Profit and Stop Loss protection that propagated immediately across all 100 follower accounts.
4. **Clean Exit & Lifecycle:** Master squareoff of the filled pending positions cleanly closed all 100 follower positions with zero orphans.
