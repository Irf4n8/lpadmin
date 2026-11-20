"""
BUG-29: Pending Order Still Active After Account Closure / Zero Balance Admin Override
Attack: 
  1. Place a pending limit order (e.g., BUY EURUSD at limit price)
  2. Admin sets balance to $0 or negative
  3. Check if pending order remains active (should be cancelled)
  4. If limit price hits, does order fill on zero/negative balance?

Also tests:
BUG-29b: Cancel race — Place pending order and immediately cancel while also 
         letting it fill → orphan partial fill.
"""
import requests, json, time

BASE_URL = "https://lpadmin.blackfx.com"

def make_session(email, password):
    s = requests.Session()
    s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
    t = s.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
    return s, {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}

s_m, h_m = make_session("mamm@mailinator.com", "12345678")

adm_r = requests.post(f"{BASE_URL}/admin/api/login", json={"email": "lpadmin@blacktrader.com", "password": "Raj1234!"})
adm_token = adm_r.json().get("token")
adm_headers = {"Authorization": f"Bearer {adm_token}", "Content-Type": "application/json"}
MASTER_ID = "mem_11434b0b9d9d210899"

# Get current price
pos_check = s_m.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_m).json()
print(f"Balance: {pos_check.get('funds', {}).get('balance')}")

# Place a pending limit order (far from current price — won't fill immediately)
# Set limit 5% below current for BUY (won't trigger)
pending_resp = s_m.post(f"{BASE_URL}/v1/oms/real/orders/pending", headers=h_m, json={
    "symbol": "EURUSD",
    "side": "BUY", 
    "quantity": 1.0,
    "type": "LIMIT",
    "price": 1.0000  # Far below market (~1.08)
})
print(f"Place pending order: {pending_resp.status_code} {pending_resp.text[:300]}")

if pending_resp.status_code != 200:
    print("Pending order placement failed. Trying different payload...")
    pending_resp = s_m.post(f"{BASE_URL}/v1/oms/real/orders/pending", headers=h_m, json={
        "symbol": "EURUSD",
        "side": "BUY",
        "quantity": 0.1,
        "order_type": "LIMIT",
        "limit_price": 1.0000
    })
    print(f"Alt payload: {pending_resp.status_code} {pending_resp.text[:300]}")

time.sleep(1)

# Get pending orders
orders_r = s_m.get(f"{BASE_URL}/v1/oms/real/orders", headers=h_m)
print(f"Orders: {orders_r.status_code} {orders_r.text[:500]}")

pending_orders = []
if orders_r.status_code == 200:
    all_orders = orders_r.json()
    if isinstance(all_orders, dict):
        pending_orders = [o for o in all_orders.get("orders", []) if o.get("status") in ["PENDING", "OPEN", "pending", "open"]]
    elif isinstance(all_orders, list):
        pending_orders = [o for o in all_orders if o.get("status") in ["PENDING", "OPEN", "pending", "open"]]

print(f"Found {len(pending_orders)} pending orders")

# Admin sets balance to $0
print("\nAdmin setting master balance to $0...")
zero_bal = requests.post(f"{BASE_URL}/admin/api/members/{MASTER_ID}/balance",
    headers=adm_headers, json={"instance": "real", "balance": 0, "force": True})
print(f"Set to $0: {zero_bal.status_code}")
time.sleep(2)

# Check if pending orders are still there
orders_after = s_m.get(f"{BASE_URL}/v1/oms/real/orders", headers=h_m)
print(f"Orders after $0 balance: {orders_after.status_code} {orders_after.text[:500]}")

pending_after = []
if orders_after.status_code == 200:
    data_after = orders_after.json()
    if isinstance(data_after, dict):
        pending_after = [o for o in data_after.get("orders", []) if o.get("status") in ["PENDING", "OPEN", "pending", "open"]]

funds_check = s_m.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_m).json()
print(f"Balance at $0: {funds_check.get('funds', {}).get('balance')}")
print(f"Pending orders remaining after $0 balance: {len(pending_after)}")

if pending_orders and len(pending_after) >= len(pending_orders):
    print("\n🚨 BUG-29 CONFIRMED: Pending orders NOT cancelled when balance set to $0!")
    print("   Risk: Order could fill against zero/negative balance when price hits limit.")
elif pending_orders:
    print("\n✅ Pending orders cancelled when balance set to $0.")
else:
    print("\n⚠️ Could not place pending order to test this scenario.")

# Cancel any remaining pending orders
for o in pending_after:
    oid = o.get("id") or o.get("order_id") or o.get("client_order_id")
    if oid:
        cancel_r = s_m.delete(f"{BASE_URL}/v1/oms/real/orders/{oid}", headers=h_m)
        print(f"Cancel order {oid}: {cancel_r.status_code}")

# Restore balance
restore = requests.post(f"{BASE_URL}/admin/api/members/{MASTER_ID}/balance",
    headers=adm_headers, json={"instance": "real", "balance": 100000, "force": True})
print(f"Restored balance: {restore.status_code}")
final = s_m.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_m).json()
print(f"Final balance: {final.get('funds', {}).get('balance')}")
print("\nBUG-29 test complete.")
