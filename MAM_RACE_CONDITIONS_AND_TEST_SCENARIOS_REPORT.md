# MAM, Copy Trading & Concurrency Completed Test Scenarios Report

## Executive Summary
This document provides an inventory and technical proof of **26 comprehensive test scenarios** executed against the live platform (`https://lpadmin.blackfx.com`), covering **Concurrency & Race Conditions, MAM / Copy Trading Lifecycle, Order Protection, and Core User Flows**.

---

## 1. Concurrency & Race Condition Scenarios

| Test ID | Scenario & Concurrency Trigger | Expected vs Actual Behavior | Status |
| :--- | :--- | :--- | :--- |
| **NET01 / BR01** | **Rapid Double BUY Click (Idempotency)**<br>• 2 concurrent BUY requests sent with identical `client_order_id`. | **Expected**: Server deduplicates request.<br>**Actual**: Server executed **two separate orders** (`ord_2d514...` & `ord_437df...`) doubling user position. | 🚨 **FAIL (P0 Bug)** |
| **AL07** | **Algo Rapid Stop & Restart**<br>• Concurrent Stop (`is_active: false`) and Start (`is_active: true`) requests. | **Expected**: Final state reflects restart.<br>**Actual**: Stop completed 3ms after Start; algo was left **silently disabled in DB**. | 🚨 **FAIL (P1 Bug)** |
| **AL05 / BR14** | **Multi-Tab Algo Save Collision**<br>• Two tabs concurrently saving differing algo code. | **Expected**: Optimistic lock / ETag check.<br>**Actual**: Silent lost update / overwrite without version check. | 🚨 **FAIL (Defect)** |
| **BR07 / NET07** | **Multi-Tab Simultaneous Square-Off**<br>• 5 threads concurrently calling `/squareoff` on the same open position. | **Expected**: Exactly 1 close succeeds; 4 fail.<br>**Actual**: **1 returned HTTP 200, 4 returned HTTP 404**. No double credit or position reversal. | ✅ **PASS** |
| **CP10** | **Master Close vs Follower Manual Close**<br>• Master square-off colliding with Follower square-off at the exact same millisecond. | **Expected**: Clean serialization.<br>**Actual**: Master closed (200), Follower rejected (404). No orphan or inverse SELL position created. | ✅ **PASS** |
| **CP04** | **Follower Unfollow vs Master BUY Collision**<br>• Follower calls `/unfollow` at the exact instant Master fires a BUY order. | **Expected**: Subscription cleanly ends; no trade copy.<br>**Actual**: Subscription ended; 0 open positions copied to follower. | ✅ **PASS** |
| **NET05 / NET08** | **Pending Order Modify vs Cancel Collision**<br>• Simultaneous PUT `/modify` and DELETE `/orders/{id}` on an active limit order. | **Expected**: Cancel terminates order without zombie.<br>**Actual**: Both returned 200; order terminated cleanly (0 pending remain). | ✅ **PASS** |
| **MARGIN-RACE** | **Multi-Order Over-Leverage Burst**<br>• 5 simultaneous BUY orders fired on an account with margin for only 1 order. | **Expected**: Margin check serializes per member.<br>**Actual**: **1 filled (200), 4 rejected (400)**. Free margin remained strictly positive. | ✅ **PASS** |
| **AL01** | **Rapid Double Creation of Algo**<br>• Rapid double-click creating an algo with the same name. | **Expected**: Unique constraint enforcement.<br>**Actual**: First returned 201; second returned 400 (`Algo with this name already exists`). | ✅ **PASS** |
| **BURST-MAM** | **Master Multi-Order Burst vs Low Follower Margin**<br>• Master fires 3 burst orders; follower has margin for only 1. | **Expected**: Follower rejects trades 2 and 3.<br>**Actual**: Follower opened 1 position; 2 rejected. Free margin remained \$21.34. | ✅ **PASS** |
| **ZERO-BAL** | **Zero-Balance Follower Replication**<br>• Follower with \$0.00 balance receives Master BUY trade. | **Expected**: Follower position rejected.<br>**Actual**: 0 positions opened on follower; \$0.00 balance intact. | ✅ **PASS** |
| **RAPID-CLOSE** | **Zero-Delay Open & Instant Square-Off**<br>• Master executes BUY and instantly closes in 0ms delay. | **Expected**: Replication queue catches up cleanly.<br>**Actual**: 0 orphaned ghost positions across all 5 follower accounts. | ✅ **PASS** |

---

## 2. MAM & Copy Trading Accounting & Lifecycle Scenarios

| Test ID | Scenario | Details & Evidence | Status |
| :--- | :--- | :--- | :--- |
| **HWM-01** | **High-Water Mark (HWM) Capital Anchoring** | When follower deposits additional capital (e.g. from \$121K to \$10M), `starting_balance` remains frozen at \$121K. During a -\$5M drawdown, `above_hwm` evaluates `True`, allowing Master to take 50% fees on losses. | 🚨 **FAIL (Critical P0)** |
| **MAM-GHOST** | **Ghost Remote Execution on Unfollow** | When follower calls `/unfollow` with active trades, status changes to `ended`. When ex-master closes position later, Master's signal still closes the detached follower's position remotely. | 🚨 **FAIL (Critical P0)** |
| **MAM-SUBLOT** | **Sub-Minimum Lot Size Handling** | Platform allows orders down to `1e-13 BTC` (100,000x smaller than 1 Satoshi), bypassing LP step-size limits. | 🚨 **FAIL (Defect)** |
| **MAM-FLEET** | **Fleet Balance & Equity Audit** | Full audit across all 201 followers (`mamf1`–`mamf100` real & paper) verifying balance, equity, and ledger consistency. | ✅ **PASS (Audited)** |

---

## 3. Order Management & Protection Engine Scenarios

| Test ID | Scenario | Details & Evidence | Status |
| :--- | :--- | :--- | :--- |
| **ORD-INV** | **Pending Order SL/TP Inversion** | `POST /orders/pending` accepts `BUY LIMIT` with `SL > limit_price` and `TP < limit_price` without rejection. | 🚨 **FAIL (Defect)** |
| **TRAIL-SL** | **Trailing Stop Parameter Validation** | Negative distance, zero distance, and extreme (1M) distances all return `400 Bad Request`. | ✅ **PASS** |
| **BASKET-ATOM**| **Basket Order Atomic Execution** | Firing a multi-leg basket where Leg 2 is invalid/stale cleanly rolled back Leg 1 (0 open positions leaked). | ✅ **PASS** |

---

## 4. End-to-End Website User Flow Scenarios (`scratch/website_flow_audit.json`)

| Flow ID | User Journey Flow | Verification Details | Status |
| :--- | :--- | :--- | :--- |
| **FLOW-01** | **Trader & Master Authentication** | Login, JWT session tokens, and Chart Token (`x-token`) generation. | ✅ **PASS** |
| **FLOW-02** | **Funds & Margin State Sync** | Real-time balance, equity, used margin, and free margin tracking. | ✅ **PASS** |
| **FLOW-03** | **MAM Follow & Relationship Binding** | Follower binds to master with multiplier and 50% share settings. | ✅ **PASS** |
| **FLOW-04** | **Order Placement & Replication** | Master market order executes and fans out instantly to active followers. | ✅ **PASS** |
| **FLOW-05** | **Position Risk Modification** | Modifying live SL and TP on active positions. | ✅ **PASS** |
| **FLOW-06** | **Square-Off & Replication Exit Cascade** | Master position close automatically cascades to active followers. | ✅ **PASS** |
| **FLOW-07** | **Trade History & Audit Trail** | P&L realization and ledger recording after trade exit. | ✅ **PASS** |

---

## Summary Statistics
- **Total Scenarios Evaluated**: 26
- **Passed / Safeguards Verified**: 19
- **Identified Defects (with live HTTP proofs)**: 7
