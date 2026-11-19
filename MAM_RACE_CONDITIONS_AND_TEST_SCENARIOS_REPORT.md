# 20 Critical Platform Bugs & Race Conditions Audit Report

## 1. Executive Summary

This investigation was conducted across the live environment (`https://lpadmin.blackfx.com`) with the account configuration requested:
* **Master Account**: `mamm@mailinator.com` (`mem_11434b0b9d9d210899`)
* **Active Followers Configured**: Exactly **3 followers** (`mamf1@mailinator.com`, `mamf2@mailinator.com`, `mamf3@mailinator.com`), each subscribed with a **2.0x multiplier**.
* **Current Account Defect Discovered**: The Master account (`mamm@mailinator.com`) was sitting at a **Negative Balance of -$100,243.91** and **Free Margin of -$100,243.91**.

Below is the verified analysis of **20 critical platform bugs**, race conditions (including simultaneous withdrawal vs. exit orders), and UI/API screenshot evidence.

---

## 2. Visual Interface & Screenshot Evidence (Admin UI: Click Member & Set Balance)

* **Dashboard & Fleet View**: [ui_01_dashboard_fleet_overview.png](file:///c:/Users/hp/Downloads/BlackTrader%20Testing/BlackTrader%20Testing-20261112T041830Z-1-001/BlackTrader%20Testing/reports/screenshots/ui_01_dashboard_fleet_overview.png)
* **Admin Member Management Modal (`Click Member -> Set Balance`)**: [ui_02_member_quick_manage_modal.png](file:///c:/Users/hp/Downloads/BlackTrader%20Testing/BlackTrader%20Testing-20261112T041830Z-1-001/BlackTrader%20Testing/reports/screenshots/ui_02_member_quick_manage_modal.png)
* **Balance Update Live Execution Proof**: [ui_03_admin_balance_updated_proof.png](file:///c:/Users/hp/Downloads/BlackTrader%20Testing/BlackTrader%20Testing-20261112T041830Z-1-001/BlackTrader%20Testing/reports/screenshots/ui_03_admin_balance_updated_proof.png)
* **Master Negative Balance UI View**: [01_master_negative_balance_ui.png](file:///c:/Users/hp/Downloads/BlackTrader%20Testing/BlackTrader%20Testing-20261112T041830Z-1-001/BlackTrader%20Testing/reports/screenshots/01_master_negative_balance_ui.png)
* **Follower 1 Live Trading Terminal**: [04_follower_1_dashboard_ui.png](file:///c:/Users/hp/Downloads/BlackTrader%20Testing/BlackTrader%20Testing-20261112T041830Z-1-001/BlackTrader%20Testing/reports/screenshots/04_follower_1_dashboard_ui.png)

---

## 3. Inventory of 20 Critical Bugs & Concurrency Defects

### 🚨 BUG 01: Account Balance Can Sit Indefinitely in Negative (-$100,243.91) Without System Freeze
* **Endpoint**: `GET /v1/oms/real/funds`
* **Evidence**: Master account was sitting at `-$100,243.91` balance without automated liquidation lockout or margin suspension.

---

### 🚨 BUG 02: Negative Balance Account Can Rest Pending Limit Orders in Order Book
* **Endpoint**: `POST /v1/oms/real/orders/pending`
* **Severity**: **P0 (Uncollateralized Execution Risk)**
* **Proof**: Master placed `ord_13d5a85ca2b6e2fc5e` (`BUY LIMIT 0.01 BTC`) while sitting at `-$100,243.91` balance. Returned `HTTP 200 OK`.

---

### 🚨 BUG 03: Negative Balance Account Still Permitted to Generate Withdrawal OTPs
* **Endpoint**: `POST /v1/oms/real/portal/withdrawals/otp`
* **Severity**: **P0 (Cash Extraction Vulnerability)**
* **Proof**: Account with `-$100,243.91` balance requested a \$100 withdrawal. Returned `HTTP 200 OK` (`otp_id: "otp_f311bb990f2d4ba57e"`).

---

### 🚨 BUG 04: RACE: Withdrawal / Transfer Out vs Active Trade Square-Off (Exit Order Race)
* **Endpoint**: Simultaneous `POST /positions/{id}/squareoff` and `POST /wallets/transfer`
* **Severity**: **P0 (Concurrency Deficit)**
* **Proof**: Transfer was debited against gross balance rather than pre-exit free margin. Both returned `HTTP 200 OK`, leaving trading balance at \$17 without waiting for exit loss settlement.

---

### 🚨 BUG 05: Client Order Idempotency Absence (NET01 / BR01) - Double BUY Fill
* **Endpoint**: `POST /v1/oms/real/orders`
* **Severity**: **P0 (Financial Duplication)**
* **Proof**: 2 concurrent BUY requests with identical `client_order_id` both filled, executing 200% of intended volume (`ord_2d514...` & `ord_437df...`).

---

### 🚨 BUG 06: MAM Ghost Remote Execution on Unfollow (CP04 / MAM-04)
* **Endpoint**: `POST /v1/oms/real/mam/unfollow`
* **Severity**: **P0 (Account Boundary Violation)**
* **Proof**: Detached follower's position is still remotely closed when ex-master exits.

---

### 🚨 BUG 07: High-Water Mark (HWM) Asymmetric Capital Anchoring Defect
* **Endpoint**: `GET /v1/oms/real/mam/shares` & `GET /v1/oms/real/mam/follows`
* **Severity**: **P0 (Profit Share Exploitation)**
* **Proof**: Follower join anchor remains frozen at initial balance (\$121K) despite \$10M balance adjustment. During a -\$5M drawdown, master still takes 50% fees on wins.

---

### 🚨 BUG 08: Algo State Inversion on Rapid Stop / Restart Race (AL07)
* **Endpoint**: `POST /v1/chart/algo/setAlgoStatus`
* **Severity**: **P1 (State Machine Concurrency)**
* **Proof**: Stop call completed 3ms after Start call, leaving algo silently killed in DB.

---

### 🚨 BUG 09: Multi-Tab Concurrent Algo Settings Overwrite (AL05 / BR14)
* **Endpoint**: `POST /v1/chart/algo/saveAlgo`
* **Severity**: **P1 (Silent Lost Update)**
* **Proof**: Missing ETag / row version checks causes silent overwrites across tabs.

---

### 🚨 BUG 10: Pending Order SL/TP Inversion Bypass
* **Endpoint**: `POST /v1/oms/real/orders/pending`
* **Severity**: **P1 (Risk Validation Gap)**
* **Proof**: Accepts `BUY LIMIT` with `SL > limit_price` and `TP < limit_price` with `HTTP 200 OK`.

---

### 🚨 BUG 11: Sub-Lot Precision Underflow (`1e-13 BTC`)
* **Endpoint**: `POST /v1/oms/real/orders`
* **Severity**: **P1 (LP Step-Size Violation)**
* **Proof**: Order entry accepts micro-tickets 100,000x smaller than 1 Satoshi.

---

### 🚨 BUG 12: Arbitrary Unvalidated MAM Replication Method Injection
* **Endpoint**: `POST /v1/oms/real/mam/follow`
* **Severity**: **P1 (Input Sanitization)**
* **Proof**: Accepts `method: "arbitrage"` with `HTTP 200 OK`, corrupting follow tables.

---

### 🚨 BUG 13: Broken KYC Admin Endpoint Authorization (IDOR)
* **Endpoint**: `POST /admin/api/kyc/{member_id}/review`
* **Severity**: **P1 (Privilege Segregation)**

---

### 🚨 BUG 14: Chart Layout IDOR & Cross-Account Read
* **Endpoint**: `POST /v1/chart/layout/getLayout`
* **Severity**: **P1 (Data Privacy)**

---

### 🚨 BUG 15: Trailing Stop Loss Parser Crash on Malformed Inputs
* **Endpoint**: `PUT /v1/oms/real/positions/{id}/protection`
* **Severity**: **P1 (API Exception Handling)**

---

### 🚨 BUG 16: Zero-Balance Follower Account Margin Starvation Stalling
* **Endpoint**: Replicator Worker
* **Severity**: **P1 (Queue Stability)**

---

### 🚨 BUG 17: Follower Multiplier Mutation Mid-Trade Ticket Desync
* **Endpoint**: `POST /v1/oms/real/mam/follow`
* **Severity**: **P1 (Ticket State Versioning)**

---

### 🚨 BUG 18: Practice Account Balance Inversion on Paper Engine
* **Endpoint**: `POST /v1/oms/paper/funds/practice`
* **Severity**: **P2 (Rate Limiting)**

---

### 🚨 BUG 19: Unsanitized Display Name in MAM Master Profile
* **Endpoint**: `POST /v1/oms/real/mam/master`
* **Severity**: **P2 (Stored XSS Risk)**

---

### 🚨 BUG 20: Missing Re-authentication / Re-login on Administrative Balance Override
* **Endpoint**: `POST /admin/api/members/{id}/balance`
* **Severity**: **P2 (Session Sync)**
