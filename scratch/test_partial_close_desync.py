import requests
import json
import time

BASE_URL = "https://lpadmin.blackfx.com"
MASTER_EMAIL = "mamm@mailinator.com"
FOLLOWER_EMAIL = "mamf92@mailinator.com"
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
print("CRITICAL DEFECT TEST: FOLLOWER PARTIAL REDUCE VS MASTER TOTAL SQUAREOFF")
print("=" * 75)

# Step 1: Follower follows Master with 1.0x multiplier
s_f.post(f"{BASE_URL}/v1/oms/real/mam/follow", headers=f_h, json={
    "master_client_id": "mem_11434b0b9d9d210899", "method": "multiplier", "multiplier": 1.0, "share_percent": 50.0
})

# Step 2: Master opens a 0.02 BTC BUY position
print("\n[Step 1] Master opens 0.02 BTC BUY...")
r_m_open = s_m.post(f"{BASE_URL}/v1/oms/real/orders", headers=m_h, json={
    "symbol": "BINANCE:BTCUSDT", "side": "BUY", "type": "MARKET", "qty": 0.02
})
m_oid = r_m_open.json().get("order", {}).get("market_order_id")
print("Master Order ID:", m_oid)

time.sleep(2)

# Step 3: Check Follower's replicated position
r_f_pos = s_f.get(f"{BASE_URL}/v1/oms/real/positions", headers=f_h)
f_positions = [p for p in r_f_pos.json().get("positions", []) if p.get("symbol") == "BINANCE:BTCUSDT"]
print("Follower Replicated Positions:", len(f_positions))
if not f_positions:
    print("Error: Follower did not replicate!")
    exit(1)

f_pos = f_positions[0]
f_oid = f_pos.get("market_order_id")
f_qty = f_pos.get("net_qty")
print(f"Follower Initial Position: ID={f_oid}, Qty={f_qty}, Side={f_pos.get('side')}")

# Step 4: Follower manually REDUCES position by 0.01 BTC (Half Close)
print(f"\n[Step 2] Follower partially reduces position by 0.01 BTC via POST /positions/{f_oid}/reduce...")
r_reduce = s_f.post(f"{BASE_URL}/v1/oms/real/positions/{f_oid}/reduce", headers=f_h, json={
    "qty": 0.01
})
print("Follower Reduce Response Status:", r_reduce.status_code)
print("Follower Reduce Response Body:", r_reduce.text)

# Verify Follower position after reduce
r_f_pos_mid = s_f.get(f"{BASE_URL}/v1/oms/real/positions", headers=f_h)
f_positions_mid = [p for p in r_f_pos_mid.json().get("positions", []) if p.get("market_order_id") == f_oid]
f_qty_mid = f_positions_mid[0].get("net_qty") if f_positions_mid else 0
print(f"Follower Remaining Qty after reduce: {f_qty_mid} BTC")

# Step 5: Master squares off their entire 0.02 BTC position!
print(f"\n[Step 3] Master squares off full 0.02 BTC position ({m_oid})...")
r_m_close = s_m.post(f"{BASE_URL}/v1/oms/real/positions/{m_oid}/squareoff", headers=m_h)
print("Master Squareoff Status:", r_m_close.status_code, r_m_close.text[:150])

time.sleep(3)

# Step 6: AUDIT FOLLOWER FINAL STATE!
# Did the follower position get closed?
# Did it invert into a -0.01 BTC SELL?
# Did it error out and leave an orphaned 0.01 BTC position?
r_f_pos_final = s_f.get(f"{BASE_URL}/v1/oms/real/positions", headers=f_h)
final_f_pos = r_f_pos_final.json().get("positions", [])

print("\n" + "=" * 75)
print("AUDIT RESULT:")
print("=" * 75)
print(f"Follower Final Open Positions Count: {len(final_f_pos)}")
for p in final_f_pos:
    print(f"  Position: ID={p.get('market_order_id')}, Side={p.get('side')}, Net Qty={p.get('net_qty')}, Unrealized PnL={p.get('unrealized_pnl')}")

# Check for position inversion
inverted = [p for p in final_f_pos if p.get("side") == "SELL"]
orphaned = [p for p in final_f_pos if p.get("side") == "BUY"]

if inverted:
    print("\n🚨🚨 CRITICAL DEFECT DETECTED: POSITION INVERSION! 🚨🚨")
    print("Master full close forced a 0.02 SELL onto follower's 0.01 BUY, creating an unintended REVERSE SHORT POSITION!")
elif orphaned:
    print("\n🚨🚨 CRITICAL DEFECT DETECTED: ORPHANED RESIDUAL POSITION! 🚨🚨")
    print("Master close failed to close or desynchronized follower's reduced position, leaving follower holding unmanaged risk!")
else:
    print("\n✅ Clean Closure: Follower remaining qty was cleanly closed without inversion.")

# Cleanup
for p in final_f_pos:
    s_f.post(f"{BASE_URL}/v1/oms/real/positions/{p.get('market_order_id')}/squareoff", headers=f_h)
s_f.post(f"{BASE_URL}/v1/oms/real/mam/unfollow", headers=f_h, json={"master_client_id": "mem_11434b0b9d9d210899"})
print("\nTest finished & cleaned up.")
