"""
BUG-23: Follower Re-Subscription During Active Master Trade
Attack: Master opens a position → follower unsubscribes → master has open trade → 
        follower re-subscribes while trade is live → check if follower gets orphan allocation
        or if the trade is replicated retroactively (unauthorized position creation).
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

MASTER_ID = "mem_11434b0b9d9d210899"
F1_ID = "mem_0ea679062ffd38adf7"

# Check current follow status of f1
follows_r = s_f1.get(f"{BASE_URL}/v1/oms/real/mam/follows", headers=h_f1)
print("F1 current follows:", follows_r.status_code, follows_r.text[:300])

# Step 1: Ensure f1 is following master
follow_r = s_f1.post(f"{BASE_URL}/v1/oms/real/mam/follow", headers=h_f1, json={
    "master_id": MASTER_ID, "multiplier": 2.0
})
print("F1 follow:", follow_r.status_code, follow_r.text[:200])
time.sleep(1)

# Step 2: Master opens a position
order_r = s_m.post(f"{BASE_URL}/v1/oms/real/orders", headers=h_m, json={
    "symbol": "EURUSD", "side": "BUY", "quantity": 0.01, "type": "MARKET"
})
print("Master open order:", order_r.status_code, order_r.text[:200])
time.sleep(2)

master_pos = s_m.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_m).json()
print("Master positions:", len(master_pos.get("positions", [])))
master_mid = None
if master_pos.get("positions"):
    master_mid = master_pos["positions"][0].get("market_order_id") or master_pos["positions"][0].get("id")

f1_pos_before = s_f1.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_f1).json()
print(f"F1 positions BEFORE unfollow: {len(f1_pos_before.get('positions', []))}")
print(f"F1 funds before: {f1_pos_before.get('funds', {}).get('balance')}")

# Step 3: F1 unfollows while master has open position
unfollow_r = s_f1.post(f"{BASE_URL}/v1/oms/real/mam/unfollow", headers=h_f1, json={
    "master_id": MASTER_ID
})
print("F1 unfollow:", unfollow_r.status_code, unfollow_r.text[:200])
time.sleep(1)

# Step 4: F1 re-subscribes while master still has position open
refollow_r = s_f1.post(f"{BASE_URL}/v1/oms/real/mam/follow", headers=h_f1, json={
    "master_id": MASTER_ID, "multiplier": 2.0
})
print("F1 RE-follow while master has open position:", refollow_r.status_code, refollow_r.text[:300])
time.sleep(3)

# Step 5: Check if F1 now has a position (should NOT — no trade was placed after subscribe)
f1_pos_after = s_f1.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_f1).json()
print(f"\n=== RESULTS ===")
print(f"F1 positions AFTER re-subscribe: {len(f1_pos_after.get('positions', []))}")
print(f"F1 funds after: {f1_pos_after.get('funds', {}).get('balance')}")
print(json.dumps(f1_pos_after.get("positions", []), indent=2)[:500])

if f1_pos_after.get("positions"):
    print("\n🚨 BUG-23 CONFIRMED: Follower got retroactive position copy on re-subscription!")
else:
    print("\n✅ BUG-23 NOT confirmed: F1 has no positions after re-subscribe.")

# Step 6: Master close all positions
if master_mid:
    sq = s_m.post(f"{BASE_URL}/v1/oms/real/positions/{master_mid}/squareoff", headers=h_m)
    print("Master squareoff:", sq.status_code)

# Check if f1 got an orphan close signal
time.sleep(2)
f1_final = s_f1.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_f1).json()
print(f"F1 final positions: {len(f1_final.get('positions', []))}")
print(f"F1 final balance: {f1_final.get('funds', {}).get('balance')}")
print("\nBUG-23 test complete.")
