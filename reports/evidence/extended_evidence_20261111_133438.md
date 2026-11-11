# Extended Copy Trading Test Suite Evidence Report (Categories I – P)

**Generated:** 2026-11-11T08:04:38.254316+00:00  
**Master Trader:** `ctmaster@mailinator.com` (`mem_aac4ca423a6925dca7`)  
**Followers Tested:** 100 (`follower1@mailinator.com` to `follower100@mailinator.com`)  
**Instance:** `paper` (Hedging)  
**Overall Result:** **10/11 SCENARIOS PASSED**

---

## 1. Executive Summary

| Category | Scenario | Status | Key Findings |
| :--- | :--- | :---: | :--- |
| **I. Copy mode and multiplier variants** | Multiplier Input Validation (Negative Blocked) | ✅ PASS | Negative multiplier (-1.5) rejected with HTTP 400 |
| **I. Copy mode and multiplier variants** | Mid-Session Multiplier Change Isolation | ✅ PASS | Trade 1 lot preserved, Trade 2 scaled to 2.5 lot |
| **J. Order types and execution edge cases** | Hedged Positions Mirror (Simultaneous Long & Short) | ✅ PASS | 100/100 verified |
| **J. Order types and execution edge cases** | Multi-Symbol Concurrent Fan-Out | ✅ PASS | 100/100 verified |
| **J. Order types and execution edge cases** | Reverse Trade Sync (Long to Short Transition) | ✅ PASS | 100/100 verified |
| **L. Follower state changes** | Follower Account Disabled Isolation | ✅ PASS | Disabled follower follower100@mailinator.com isolated, remaining 99 unharmed |
| **L. Follower state changes** | Follower Balance Change Mid-Trade | ✅ PASS | Balance changed mid-trade, lot preserved (0.1 lot) |
| **L. Follower state changes** | Bulk Unfollow and Bulk Re-Follow | ❌ FAIL | Unfollow clean: False, Re-follow clean: True |
| **N. Data integrity and idempotency** | Order ID Traceability & Copy Ref Mapping | ✅ PASS | 100/100 mapped to master ord_992b6d2f10be60b27f |
| **P. Security and permissions** | Security, Permissions, IDOR & Injection Defense | ✅ PASS | 401 on missing/invalid token, IDOR blocked (404), SQLi rejected (400) |
| **Accounting & Teardown** | Final Teardown & Zero Orphan Verification | ✅ PASS | 0 orphans |

---

## 2. Platform Architecture & Security Insights Confirmed

1. **Input Validation:** Multipliers below `0.01` return HTTP 400 with `"The multiplier can't be below 0.01."`.
2. **Dynamic Multiplier Scalability:** Changing a follower's multiplier mid-session keeps existing positions strictly untouched while routing subsequent orders through the new multiplier.
3. **Hedged Mirroring:** Follower accounts cleanly mirror simultaneously active Long and Short positions on the same contract without netting interference.
4. **Multi-Symbol Concurrency:** Concurrent orders on distinct contracts (e.g. `BTCUSDT` and `ETHUSDT`) mirror in parallel without symbol cross-contamination.
5. **Account Isolation:** When an individual follower is disabled/blocked via the admin API, the copy trading engine isolates the account and continues fan-out to the remaining active followers uninterrupted.
6. **Balance Adjustments Mid-Trade:** Admin capital injections or withdrawals mid-trade do not invalidate or alter active copied positions.
7. **Traceability & Auditing:** Follower order records retain a `copy_ref` field referencing `"-<master_market_order_id>"` and `source: "copy"`.
8. **IDOR & Session Defense:** Followers cannot execute actions against master order identifiers; requests without valid Bearer tokens are rejected with HTTP 401.
