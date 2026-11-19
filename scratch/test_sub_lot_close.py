import requests
import json
import time

BASE_URL = "https://lpadmin.blackfx.com"
MASTER_EMAIL = "mamm@mailinator.com"
FOLLOWER_EMAIL = "mamf1@mailinator.com"
PWD = "12345678"

s_m = requests.Session()
s_m.post(f"{BASE_URL}/api/auth/login", json={"email": MASTER_EMAIL, "password": PWD})
m_tok = s_m.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
m_h = {"Authorization": f"Bearer {m_tok}", "Content-Type": "application/json"}

s_f = requests.Session()
s_f.post(f"{BASE_URL}/api/auth/login", json={"email": FOLLOWER_EMAIL, "password": PWD})
f_tok = s_f.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
f_h = {"Authorization": f"Bearer {f_tok}", "Content-Type": "application/json"}

# Place 0.00001 BTC order directly on follower
r_direct = s_f.post(f"{BASE_URL}/v1/oms/real/orders", headers=f_h, json={
    "symbol": "BINANCE:BTCUSDT",
    "side": "BUY",
    "type": "MARKET",
    "qty": 0.00001
})
print("Direct 0.00001 BTC order:", r_direct.status_code, r_direct.text)
mkt_id = r_direct.json().get("order", {}).get("market_order_id")

if mkt_id:
    # Try squaring off
    r_sq = s_f.post(f"{BASE_URL}/v1/oms/real/positions/{mkt_id}/squareoff", headers=f_h)
    print("Squareoff 0.00001 BTC position:", r_sq.status_code, r_sq.text)

# What about 0.000000001 BTC (1 Satoshi or sub-satoshi)?
r_nano = s_f.post(f"{BASE_URL}/v1/oms/real/orders", headers=f_h, json={
    "symbol": "BINANCE:BTCUSDT",
    "side": "BUY",
    "type": "MARKET",
    "qty": 0.0000000000001
})
print("Direct 1e-13 BTC order:", r_nano.status_code, r_nano.text)
nano_id = r_nano.json().get("order", {}).get("market_order_id")
if nano_id:
    s_f.post(f"{BASE_URL}/v1/oms/real/positions/{nano_id}/squareoff", headers=f_h)
