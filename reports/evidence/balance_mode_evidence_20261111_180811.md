# Balance-Based Copy Trading 100-Follower Test Evidence Report

**Generated:** 2026-11-11T12:38:11.911961+00:00  
**Master Trader:** `ctmaster@mailinator.com` (`mem_aac4ca423a6925dca7`)  
**Followers Tested:** 100 (`follower1@mailinator.com` to `follower100@mailinator.com`)  
**Trading Symbol:** `BINANCE:BTCUSDT.P` (Lot per order: 0.1)  
**Copy Trading Mode:** `balance` (Follower Lot = Master Lot × Follower Balance / Master Balance)  
**Orders per Scenario:** ≥ 10 orders  
**Instance:** `paper` (Hedging)  
**Overall Result:** **10/10 SCENARIOS PASSED**

---

## 1. Executive Summary

| Scenario | Orders Placed | Followers Verified | Status | Details |
| :--- | :---: | :---: | :---: | :--- |
| **Market BUY Fan-out (10 orders)** | 10 | 100/100 | ✅ PASS | 10 orders placed, 100/100 followers verified |
| **Partial Close (10 orders reduced)** | 10 | 100/100 | ✅ PASS | 10 orders reduced across 100/100 followers |
| **Full Close (10 orders closed)** | 10 | 100/100 | ✅ PASS | 10 orders closed across 100/100 followers |
| **Take Profit / Stop Loss Propagation (10 orders)** | 10 | 100/100 | ✅ PASS | 10 orders verified across 100/100 followers |
| **Pending Limit Orders & Cancel (10 orders)** | 10 | 100/100 | ✅ PASS | 100/100 passed |
| **Rapid Burst (10 orders)** | 10 | 100/100 | ✅ PASS |  |
| **Market SELL Fan-out (10 orders)** | 10 | 100/100 | ✅ PASS | 10 orders placed, 100/100 followers verified |
| **Follower Manual Close Isolation** | 10 | 100/100 | ✅ PASS |  |
| **Follow Mid-Trade Isolation (No Retroactive Copying)** | 10 | 100/100 | ✅ PASS |  |
| **Unfollow Mid-Trade Behavior Probe** | 10 | 100/100 | ℹ️ OBSERVED | Position was closed on master close |
| **Final Teardown & Zero Orphan Verification** | 10 | 100/100 | ✅ PASS | 0 orphans |

---

## 2. Transition & Dynamic Balance Scaling Verification
1. **Full Leave (Unfollow):** All 100 followers cleanly unfollowed master; active links confirmed dropped to **0**.
2. **Capital Configuration:**
   * Master Balance: `100,000,000.00` ($1.0\times$)
   * Followers 1–25 Balance: `100,000,000.00` (Ratio: **$1.0\times$** -> **0.10 lot**)
   * Followers 26–50 Balance: `200,000,000.00` (Ratio: **$2.0\times$** -> **0.20 lot**)
   * Followers 51–75 Balance: `300,000,000.00` (Ratio: **$3.0\times$** -> **0.30 lot**)
   * Followers 76–100 Balance: `50,000,000.00` (Ratio: **$0.5\times$** -> **0.05 lot**)
3. **Balance Join:** All 100 followers re-linked with `method='balance'`; confirmed active links restored to **100**.
4. **Execution Sizing:** Each master order of `0.10` lot automatically scaled across all 100 followers in exact proportion to their balance ratios.
