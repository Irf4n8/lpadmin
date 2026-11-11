# BlackTrader API & Platform Architecture Documentation

## 1. Environment & Architecture Overview
* **Platform:** White-label crypto/FX trading terminal and OMS powered by BlackTrader.
* **Central Super-Admin:** `https://chartv2.blacktrader.com`
* **Client Admin Instance:** `lpadmin` (#19) at `https://lpadmin.blackfx.com/blackadmin`
* **Trader Terminal / Dashboard:** `https://lpadmin.blackfx.com/dashboard`
* **Broker Token:** `bt_597a3fbcc2800eafc11a9b14d503e69cb1f198ac34caefa5111b871afd1b6ca6`

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

