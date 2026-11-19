import requests
import json
import time

BASE_URL = "https://lpadmin.blackfx.com"
MASTER_EMAIL = "mamm@mailinator.com"
FOLLOWER_EMAIL = "mamf89@mailinator.com"
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

print("=" * 75)
print("TEST CP05: FOLLOWER CHANGES MULTIPLIER MID-TRADE VS MASTER SQUAREOFF")
print("=" * 75)

# Step 1: Follower follows Master with multiplier 1.0x
s_f.post(f"{BASE_URL}/v1/oms/real/mam/follow", headers=f_h, json={
    "master_client_id": "mem_11434b0b9d9d210899", "method": "multiplier", "multiplier": 1.0, "share_percent": 50.0
})

# Step 2: Master opens 0.01 BTC BUY
print("\n[Step 1] Master opens 0.01 BTC BUY...")
r_open = s_m.post(f"{BASE_URL}/v1/oms/real/orders", headers=m_h, json={
    "symbol": "BINANCE:BTCUSDT", "side": "BUY", "type": "MARKET", "qty": 0.01
})
m_oid = r_open.json().get("order", {}).get("market_order_id")
print("Master Order ID:", m_oid)
time.sleep(2)

# Verify Follower position
r_f_pos = s_f.get(f"{BASE_URL}/v1/oms/real/positions", headers=f_h)
f_pos = next((p for p in r_f_pos.json().get("positions", []) if p.get("symbol") == "BINANCE:BTCUSDT"), None)
print("Follower Initial Copied Position:", f_pos.get("market_order_id"), "Qty:", f_pos.get("net_qty"))

# Step 3: Follower changes multiplier to 5.0x WHILE POSITION IS OPEN!
print("\n[Step 2] Follower updates multiplier to 5.0x mid-trade...")
r_update = s_f.post(f"{BASE_URL}/v1/oms/real/mam/follow", headers=f_h, json={
    "master_client_id": "mem_11434b0b9d9d210899", "method": "multiplier", "multiplier": 5.0, "share_percent": 50.0
})
print("Update Multiplier Status:", r_update.status_code, r_update.text)

# Step 4: Master closes position
print("\n[Step 3] Master squares off position...")
r_close = s_m.post(f"{BASE_URL}/v1/oms/real/positions/{m_oid}/squareoff", headers=m_h)
print("Master Close Status:", r_close.status_code, r_close.text[:150])
time.sleep(2)

# Step 5: Audit Follower State
r_f_final = s_f.get(f"{BASE_URL}/v1/oms/real/positions", headers=f_h)
final_positions = r_f_final.json().get("positions", [])
print("\nFollower Open Positions Remaining:", len(final_positions))
for p in final_positions:
    print(f"  Residual: ID={p.get('market_order_id')}, Side={p.get('side')}, Qty={p.get('net_qty')}")

# Cleanup
for p in final_positions:
    s_f.post(f"{BASE_URL}/v1/oms/real/positions/{p.get('market_order_id')}/squareoff", headers=f_h)
s_f.post(f"{BASE_URL}/v1/oms/real/mam/unfollow", headers=f_h, json={"master_client_id": "mem_11434b0b9d9d210899"})
print("\nAudit completed.")
