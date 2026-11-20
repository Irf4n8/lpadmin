"""
BUG-28: MAM Master Stop-Out Propagation — Does stop-out cascade to followers?
Attack: 
  1. Followers are following master (mamf1, mamf2, mamf3)
  2. Master opens a large position that consumes most margin
  3. Admin reduces master balance to below stop-out threshold
  4. Check: does system auto-close master's positions? 
  5. Check: do followers' positions also close (cascade)?
  6. Check: are followers' margins intact?
"""
import requests, json, time

BASE_URL = "https://lpadmin.blackfx.com"

def make_session(email, password):
    s = requests.Session()
    s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
    t = s.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
    return s, {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}

s_m, h_m = make_session("mamm@mailinator.com", "12345678")
s_f1, h_f1 = make_session("mamf1@mailinator.com", "12345678")

# Admin auth
adm_r = requests.post(f"{BASE_URL}/admin/api/login", json={"email": "lpadmin@blacktrader.com", "password": "Raj1234!"})
adm_token = adm_r.json().get("token")
adm_headers = {"Authorization": f"Bearer {adm_token}", "Content-Type": "application/json"}

MASTER_ID = "mem_11434b0b9d9d210899"
F1_ID = "mem_0ea679062ffd38adf7"

# Ensure f1 is following master
follow_r = s_f1.post(f"{BASE_URL}/v1/oms/real/mam/follow", headers=h_f1, json={
    "master_id": MASTER_ID, "multiplier": 1.0
})
print("F1 follow:", follow_r.status_code, follow_r.text[:100])
time.sleep(1)

# Set master balance to $5000 and open $4000 margin position (to be near stop-out)
set_bal = requests.post(f"{BASE_URL}/admin/api/members/{MASTER_ID}/balance",
    headers=adm_headers, json={"instance": "real", "balance": 5000, "force": True})
print(f"Set master balance to $5000: {set_bal.status_code}")
time.sleep(1)

# Check master funds
pre_m = s_m.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_m).json()
print(f"Master balance: {pre_m.get('funds', {}).get('balance')}, stop_out: {pre_m.get('funds', {}).get('stop_out_level')}")

# Open large position  
order = s_m.post(f"{BASE_URL}/v1/oms/real/orders", headers=h_m, json={
    "symbol": "BTCUSD", "side": "BUY", "quantity": 0.05, "type": "MARKET"
})
print(f"Master open order: {order.status_code} {order.text[:200]}")
time.sleep(3)

mid_data = s_m.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_m).json()
print(f"Master after open: positions={len(mid_data.get('positions', []))}, used_margin={mid_data.get('funds', {}).get('used_margin')}, free_margin={mid_data.get('funds', {}).get('free_margin')}")

f1_mid = s_f1.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_f1).json()
print(f"F1 after master opens: positions={len(f1_mid.get('positions', []))}")
master_positions_before = mid_data.get("positions", [])

# Now admin reduces master balance to trigger stop-out (below 50% margin level)
# Stop-out fires when equity < 50% of used_margin
used_margin = mid_data.get("funds", {}).get("used_margin", 500)
trigger_balance = used_margin * 0.3  # Well below 50% stop-out
print(f"\nTriggering stop-out: setting balance to ${trigger_balance} (stop-out at {used_margin * 0.5})")

stop_trigger = requests.post(f"{BASE_URL}/admin/api/members/{MASTER_ID}/balance",
    headers=adm_headers, json={"instance": "real", "balance": trigger_balance, "force": True})
print(f"Stop-out trigger set: {stop_trigger.status_code}")

# Wait for stop-out engine to fire
print("Waiting 10s for stop-out engine...")
time.sleep(10)

# Check master state after stop-out
post_m = s_m.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_m).json()
print(f"\n=== POST STOP-OUT ===")
print(f"Master positions: {len(post_m.get('positions', []))}")
print(f"Master balance: {post_m.get('funds', {}).get('balance')}")
print(f"Master equity: {post_m.get('funds', {}).get('equity')}")

post_f1 = s_f1.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_f1).json()
print(f"F1 positions: {len(post_f1.get('positions', []))}")
print(f"F1 balance: {post_f1.get('funds', {}).get('balance')}")

master_positions_after = post_m.get("positions", [])
f1_positions_after = post_f1.get("positions", [])

print("\n=== ANALYSIS ===")
if len(master_positions_before) > 0 and len(master_positions_after) == 0:
    print("✅ Master stop-out fired (positions closed)")
    if len(f1_positions_after) > 0:
        print("🚨 BUG-28 CONFIRMED: Follower positions NOT closed after master stop-out! (Orphaned positions)")
    else:
        print("✅ Follower positions also closed (cascade works)")
elif len(master_positions_before) > 0 and len(master_positions_after) > 0:
    print("🚨 BUG-28 VARIANT: Master stop-out did NOT fire despite being below threshold!")
    print(f"   Master equity should trigger stop-out but positions remain open")

# Restore everything
print("\n=== CLEANUP ===")
# Close any remaining positions
for p in master_positions_after:
    mid = p.get("market_order_id") or p.get("id")
    sq = s_m.post(f"{BASE_URL}/v1/oms/real/positions/{mid}/squareoff", headers=h_m)
    print(f"Master cleanup: {sq.status_code}")
for p in f1_positions_after:
    mid = p.get("market_order_id") or p.get("id")
    sq = s_f1.post(f"{BASE_URL}/v1/oms/real/positions/{mid}/squareoff", headers=h_f1)
    print(f"F1 cleanup: {sq.status_code}")

# Restore balances
requests.post(f"{BASE_URL}/admin/api/members/{MASTER_ID}/balance",
    headers=adm_headers, json={"instance": "real", "balance": 100000, "force": True})
requests.post(f"{BASE_URL}/admin/api/members/{F1_ID}/balance",
    headers=adm_headers, json={"instance": "real", "balance": 10000, "force": True})
print("Balances restored.")
print("\nBUG-28 test complete.")
