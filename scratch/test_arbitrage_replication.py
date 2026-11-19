import requests
import json
import time

BASE_URL = "https://lpadmin.blackfx.com"
MASTER_EMAIL = "mamm@mailinator.com"
FOLLOWER_EMAIL = "mamf93@mailinator.com"
PWD = "12345678"

# Follower Login
s_f = requests.Session()
s_f.post(f"{BASE_URL}/api/auth/login", json={"email": FOLLOWER_EMAIL, "password": PWD})
f_tok = s_f.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
f_h = {"Authorization": f"Bearer {f_tok}", "Content-Type": "application/json"}

# Master Login
s_m = requests.Session()
s_m.post(f"{BASE_URL}/api/auth/login", json={"email": MASTER_EMAIL, "password": PWD})
m_tok = s_m.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
m_h = {"Authorization": f"Bearer {m_tok}", "Content-Type": "application/json"}

print("=" * 70)
print("TESTING REPLICATION ENGINE BEHAVIOR ON INVALID METHOD 'arbitrage'")
print("=" * 70)

# Follower joins with method='arbitrage'
s_f.post(f"{BASE_URL}/v1/oms/real/mam/unfollow", headers=f_h, json={"master_client_id": "mem_11434b0b9d9d210899"})
r_fol = s_f.post(f"{BASE_URL}/v1/oms/real/mam/follow", headers=f_h, json={
    "master_client_id": "mem_11434b0b9d9d210899",
    "method": "arbitrage",
    "multiplier": 1.0,
    "share_percent": 50.0
})
print("Follow status with method='arbitrage':", r_fol.status_code, r_fol.text)

# Master opens trade
print("\nMaster placing 0.01 BUY order...")
r_open = s_m.post(f"{BASE_URL}/v1/oms/real/orders", headers=m_h, json={
    "symbol": "BINANCE:BTCUSDT", "side": "BUY", "type": "MARKET", "qty": 0.01
})
print("Master Order Status:", r_open.status_code, r_open.text)
m_oid = r_open.json().get("order", {}).get("market_order_id")

time.sleep(2)

# Check Follower positions
r_f_pos = s_f.get(f"{BASE_URL}/v1/oms/real/positions", headers=f_h)
f_positions = r_f_pos.json().get("positions", [])
print(f"\nFollower Open Positions Count: {len(f_positions)}")
if f_positions:
    print("Follower Position details:", f_positions)
else:
    print("Follower position NOT replicated! (Replication silent failure / drop)")

# Cleanup
if m_oid:
    s_m.post(f"{BASE_URL}/v1/oms/real/positions/{m_oid}/squareoff", headers=m_h)
for p in f_positions:
    s_f.post(f"{BASE_URL}/v1/oms/real/positions/{p.get('market_order_id')}/squareoff", headers=f_h)
s_f.post(f"{BASE_URL}/v1/oms/real/mam/unfollow", headers=f_h, json={"master_client_id": "mem_11434b0b9d9d210899"})
print("\nTest completed & cleaned up.")
