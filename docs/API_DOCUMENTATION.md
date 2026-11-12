# BlackTrader API & Platform Architecture Documentation

## 1. Environment & Architecture Overview
* **Platform:** White-label crypto/FX trading terminal and OMS powered by BlackTrader.
* **Central Super-Admin:** `https://chartv2.blacktrader.com`
* **Client Admin Instance:** `lpadmin` (#19) at `https://lpadmin.blackfx.com/blackadmin`
* **Trader Terminal / Dashboard:** `https://lpadmin.blackfx.com/dashboard`
* **Broker Token:** `bt_[REDACTED - rotate if this was ever secret]`

---

## 2. Authentication Systems

### A. Client Admin Authentication
* **Endpoint:** `POST /admin/api/login`
* **Payload:** `{"email": "lpadmin@blacktrader.com", "password": "...", "remember": true}`
* **Storage:** Browser receives bearer token and stores it in `localStorage` under `oms_admin_token`.
* **Subsequent Calls:** `Authorization: Bearer <oms_admin_token>`.

### B. Trader Portal & Chart Authentication
* **Trader Login:** `POST /api/auth/login` with `{"email": "...", "password": "..."}`
* **Session Cookie:** Server responds with `Set-Cookie: bt_trader=...`
* **Chart Token Minting:** `POST /api/auth/chart-token` (passes `bt_trader` cookie).
* **OMS Bearer Token:** Server responds with `{"token": "<chart_bearer_token>", "expires_at": "..."}`.
* **Subsequent OMS Calls:** `Authorization: Bearer <chart_bearer_token>`.

---

## 3. Core API Endpoints

### 3.1 Members Management
* **List All Members:** `GET /admin/api/members`
* **Create Member:** `POST /admin/api/members`
  * Body: `{"email": "follower1@mailinator.com", "password": "...", "name": ""}`
* **Set Member Balance:** `POST /admin/api/members/{member_id}/balance`
  * Body: `{"instance": "paper"|"real", "balance": 100000000, "remark": "...", "force": true}`

### 3.2 Copy-Trading Management
* **List Active Masters:** `GET /v1/oms/{instance}/copy/masters` (`instance` can be `paper` or `real`).
* **Follow a Master:** `POST /v1/oms/{instance}/copy/follow`
  * Body:
    ```json
    {
      "master_client_id": "mem_aac4ca423a6925dca7",
      "method": "multiplier",
      "multiplier": 1.0,
      "reverse": false,
      "copy_mode": "public"
    }
    ```



## A-book / B-book (per account)

* Each member has `"book": "a" | "b"` (visible in `GET /admin/api/members`).
* **A-book**: the member's *real* orders are executed at the liquidity provider. **B-book**: booked on the platform's
  own engine. Paper accounts are always booked internally, so the setting only changes real-instance routing.
* Change it: `POST /admin/api/members/{member_id}/book` with `{"book": "a"}` or `{"book": "b"}` (admin bearer token).
* Dashboard: `GET /api/books`, `POST /api/books/switch {book, scope: master|followers|all|emails, start, end, confirm}`.
  Limited to the configured master + followers, returns 412 without `confirm`, 409 while a run is active, and verifies
  every account by reading it back (HTTP 207 if some did not switch).
