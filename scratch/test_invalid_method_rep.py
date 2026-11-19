import requests
import json
import time

BASE_URL = "https://lpadmin.blackfx.com"
MASTER_EMAIL = "mamm@mailinator.com"
FOLLOWER_EMAIL = "mamf1@mailinator.com"
PWD = "12345678"

# Login
m_s = requests.Session()
m_s.post(f"{BASE_URL}/api/auth/login", json={"email": MASTER_EMAIL, "password": PWD})
m_tok = m_s.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
m_headers = {"Authorization": f"Bearer {m_tok}", "Content-Type": "application/json"}

f_s = requests.Session()
f_s.post(f"{BASE_URL}/api/auth/login", json={"email": FOLLOWER_EMAIL, "password": PWD})
f_tok = f_s.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
f_headers = {"Authorization": f"Bearer {f_tok}", "Content-Type": "application/json"}

# Follower is currently following with method: "martingale_hack"
print("Master placing order of 0.05 BTC...")
r_m_ord = m_s.post(f"{BASE_URL}/v1/oms/real/orders", headers=m_headers, json={
    "symbol": "BINANCE:BTCUSDT", "side": "BUY", "type": "MARKET", "qty": 0.05
})
print("Master order:", r_m_ord.status_code, r_m_ord.json())
m_ord_id = r_m_ord.json().get("order", {}).get("market_order_id")

time.sleep(1)

# Check follower positions
r_f_pos = f_s.get(f"{BASE_URL}/v1/oms/real/positions", headers=f_headers)
print("Follower positions:", r_f_pos.status_code, r_f_pos.json())

# Cleanup master order
if m_ord_id:
    m_s.post(f"{BASE_URL}/v1/oms/real/positions/{m_ord_id}/squareoff", headers=m_headers)

# Square off follower if any
for p in r_f_pos.json().get("positions", []):
    f_s.post(f"{BASE_URL}/v1/oms/real/positions/{p.get('market_order_id')}/squareoff", headers=f_headers)

# Reset follower cleanly
f_s.post(f"{BASE_URL}/v1/oms/real/mam/follow", headers=f_headers, json={
    "master_client_id": "mem_11434b0b9d9d210899", "method": "equity", "multiplier": 1.0, "share_percent": 50.0
})
