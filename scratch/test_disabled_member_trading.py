import requests
import json
import time

BASE_URL = "https://lpadmin.blackfx.com"
ADMIN_EMAIL = "lpadmin@blacktrader.com"
ADMIN_PASSWORD = "Raj1234!"
TEST_FOLLOWER = "mamf99@mailinator.com"
PWD = "12345678"

# 1. Admin login
adm_s = requests.Session()
adm_s.post(f"{BASE_URL}/admin/api/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "remember": True})
adm_tok = adm_s.post(f"{BASE_URL}/admin/api/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}).json().get("token")
adm_headers = {"Authorization": f"Bearer {adm_tok}", "Content-Type": "application/json"}

# 2. Get mamf99 member_id
m_list = adm_s.get(f"{BASE_URL}/admin/api/members", headers=adm_headers).json().get("members", [])
f99_info = next((m for m in m_list if m.get("email") == TEST_FOLLOWER), None)
print(f"Target Follower {TEST_FOLLOWER}: member_id={f99_info.get('member_id')}, current_status={f99_info.get('status')}")
f99_id = f99_info.get("member_id")

# 3. Disable the member via Admin API
r_status = adm_s.post(f"{BASE_URL}/admin/api/members/{f99_id}/status", headers=adm_headers, json={"status": "disabled"})
print(f"Set status to 'disabled': {r_status.status_code}, response: {r_status.text}")

# 4. Check if disabled follower can still authenticate!
f_s = requests.Session()
r_login = f_s.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_FOLLOWER, "password": PWD})
print(f"Disabled member login attempt: {r_login.status_code}, body: {r_login.text}")

# 5. Check if disabled follower can mint chart token and place an order!
r_tok = f_s.post(f"{BASE_URL}/api/auth/chart-token")
print(f"Disabled member chart-token attempt: {r_tok.status_code}")
f99_tok = r_tok.json().get("token")
f99_headers = {"Authorization": f"Bearer {f99_tok}", "Content-Type": "application/json"}

r_ord = f_s.post(f"{BASE_URL}/v1/oms/real/orders", headers=f99_headers, json={
    "symbol": "BINANCE:BTCUSDT", "side": "BUY", "type": "MARKET", "qty": 0.01
})
print(f"Disabled member order placement: {r_ord.status_code}, body: {r_ord.text}")

# 6. Check if MAM Master trade replicates to the DISABLED follower!
m_s = requests.Session()
m_s.post(f"{BASE_URL}/api/auth/login", json={"email": "mamm@mailinator.com", "password": PWD})
m_tok = m_s.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
m_headers = {"Authorization": f"Bearer {m_tok}", "Content-Type": "application/json"}

# Master places order
r_m_ord = m_s.post(f"{BASE_URL}/v1/oms/real/orders", headers=m_headers, json={
    "symbol": "BINANCE:BTCUSDT", "side": "BUY", "type": "MARKET", "qty": 0.01
})
print(f"Master order placement: {r_m_ord.status_code}")
m_mkt_id = r_m_ord.json().get("order", {}).get("market_order_id")

time.sleep(1)

# Check if disabled follower received replicated position!
r_f_pos = f_s.get(f"{BASE_URL}/v1/oms/real/positions", headers=f99_headers)
pos_list = r_f_pos.json().get("positions", [])
print(f"CRITICAL CHECK: Replicated positions on DISABLED member: {len(pos_list)}")
for p in pos_list:
    print(f"  Replicated Position: ID={p.get('position_id')}, Qty={p.get('net_qty')}, Symbol={p.get('symbol')}")

# Clean up
if m_mkt_id:
    m_s.post(f"{BASE_URL}/v1/oms/real/positions/{m_mkt_id}/squareoff", headers=m_headers)
for p in pos_list:
    f_s.post(f"{BASE_URL}/v1/oms/real/positions/{p.get('market_order_id')}/squareoff", headers=f99_headers)

# Re-enable mamf99
adm_s.post(f"{BASE_URL}/admin/api/members/{f99_id}/status", headers=adm_headers, json={"status": "active"})
print(f"mamf99 restored to active status.")
