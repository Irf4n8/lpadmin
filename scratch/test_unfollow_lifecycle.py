import requests
import json
import time

BASE_URL = "https://lpadmin.blackfx.com"
MASTER_EMAIL = "mamm@mailinator.com"
FOLLOWER_EMAIL = "mamf1@mailinator.com"
PWD = "12345678"
INSTANCE = "real"
SYMBOL = "BINANCE:BTCUSDT"

s_m = requests.Session()
s_m.post(f"{BASE_URL}/api/auth/login", json={"email": MASTER_EMAIL, "password": PWD})
m_tok = s_m.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
m_h = {"Authorization": f"Bearer {m_tok}", "Content-Type": "application/json"}

s_f = requests.Session()
s_f.post(f"{BASE_URL}/api/auth/login", json={"email": FOLLOWER_EMAIL, "password": PWD})
f_tok = s_f.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
f_h = {"Authorization": f"Bearer {f_tok}", "Content-Type": "application/json"}

# 1. Follow
s_f.post(f"{BASE_URL}/v1/oms/{INSTANCE}/mam/follow", headers=f_h, json={
    "master_client_id": "mem_11434b0b9d9d210899", "method": "multiplier", "multiplier": 1.0, "share_percent": 50.0
})

# 2. Master opens position
r_m_open = s_m.post(f"{BASE_URL}/v1/oms/{INSTANCE}/orders", headers=m_h, json={
    "symbol": SYMBOL, "side": "BUY", "type": "MARKET", "qty": 0.01
})
m_id = r_m_open.json().get("order", {}).get("market_order_id")
time.sleep(1)

# Check follower has position
r_f_pos = s_f.get(f"{BASE_URL}/v1/oms/{INSTANCE}/positions", headers=f_h)
f_pos = [p for p in r_f_pos.json().get("positions", []) if p.get("symbol") == SYMBOL]
print(f"Follower has copied position: {len(f_pos)}")
f_pos_id = f_pos[0].get("position_id") if f_pos else None

# 3. Follower UNFOLLOWS
r_unfol = s_f.post(f"{BASE_URL}/v1/oms/{INSTANCE}/mam/unfollow", headers=f_h, json={
    "master_client_id": "mem_11434b0b9d9d210899"
})
print("Unfollow response:", r_unfol.status_code, r_unfol.json())

# Check follower follows status
r_status = s_f.get(f"{BASE_URL}/v1/oms/{INSTANCE}/mam/follows", headers=f_h)
print("Follower follows status after unfollow:", r_status.json().get("following"))

# 4. Master squares off after follower has left!
r_m_close = s_m.post(f"{BASE_URL}/v1/oms/{INSTANCE}/positions/{m_id}/squareoff", headers=m_h)
print("Master squared off:", r_m_close.status_code, r_m_close.json())
time.sleep(1)

# Check what happened to follower position!
r_f_after = s_f.get(f"{BASE_URL}/v1/oms/{INSTANCE}/positions", headers=f_h)
f_pos_remaining = [p for p in r_f_after.json().get("positions", []) if p.get("symbol") == SYMBOL]
print(f"Follower position remaining after ex-master close: {len(f_pos_remaining)}")

# Re-link follower cleanly
s_f.post(f"{BASE_URL}/v1/oms/{INSTANCE}/mam/follow", headers=f_h, json={
    "master_client_id": "mem_11434b0b9d9d210899", "method": "multiplier", "multiplier": 1.0, "share_percent": 50.0
})
