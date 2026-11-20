"""
BUG-26 (revised): Concurrent Squareoff from Two Sessions (Same Position) → Double-Close
Using EURUSD since BTCUSD feed is stale.
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

pre = s_m1.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_m1).json()
pre_balance = pre.get("funds", {}).get("balance")
print(f"Pre-test balance: {pre_balance}")

# Open EURUSD position
order = s_m1.post(f"{BASE_URL}/v1/oms/real/orders", headers=h_m1, json={
    "symbol": "EURUSD", "side": "BUY", "quantity": 1.0, "type": "MARKET"
})
print(f"Open EURUSD: {order.status_code} {order.text[:300]}")
time.sleep(2)

pos_data = s_m1.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_m1).json()
positions = pos_data.get("positions", [])
print(f"Positions: {len(positions)}")
if not positions:
    print("No position. Abort.")
    exit(1)

mid = positions[0].get("market_order_id") or positions[0].get("id")
open_price = positions[0].get("avg_entry_price")
margin_used = positions[0].get("margin_used")
print(f"Position: {mid}, open_price={open_price}, margin_used={margin_used}")

results = {}

def squareoff(session, headers, position_id, label):
    r = session.post(f"{BASE_URL}/v1/oms/real/positions/{position_id}/squareoff", headers=headers)
    results[label] = {"status": r.status_code, "body": r.text[:400]}
    print(f"[{label}] Squareoff: {r.status_code} {r.text[:250]}")
    return r.status_code

with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
    f1 = ex.submit(squareoff, s_m1, h_m1, mid, "SESSION_A")
    f2 = ex.submit(squareoff, s_m2, h_m2, mid, "SESSION_B")
    r1 = f1.result()
    r2 = f2.result()

time.sleep(3)
post = s_m1.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_m1).json()
post_balance = post.get("funds", {}).get("balance")
post_equity = post.get("funds", {}).get("equity")
print(f"\nPost-test: balance={post_balance}, equity={post_equity}")
print(f"Post positions: {len(post.get('positions', []))}")

print("\n=== RESULTS ===")
print(json.dumps(results, indent=2))

if r1 == 200 and r2 == 200:
    print("\n🚨 BUG-26 CONFIRMED: Both squareoff requests returned HTTP 200!")
    delta = post_balance - pre_balance if post_balance and pre_balance else 0
    print(f"   Balance delta: {delta:.4f}")
    # Check order history for double close
    orders = s_m1.get(f"{BASE_URL}/v1/oms/real/orders", headers=h_m1).json()
    print(f"   Order history count: {orders.get('count', 'N/A') if isinstance(orders, dict) else len(orders)}")
else:
    print(f"\n✅ BUG-26 NOT confirmed: responses = {r1}, {r2}")

print("\nBUG-26 test complete.")
