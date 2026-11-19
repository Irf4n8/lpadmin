import requests, time

base_url = "https://lpadmin.blackfx.com/v1"
instance = "real"
email = "mamm@mailinator.com"
password = "12345678"

print("--- Step 1: Sign in ---")
r_login = requests.post(f"{base_url}/oms/_auth/login", json={"email": email, "password": password})
print("Login status:", r_login.status_code)
login_data = r_login.json()
token = login_data["token"]
print("Auth token:", token)
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

print("\n--- Step 2: Place Bulk Market Orders ---")
market_order_ids = []
symbol = "BINANCE:BTCUSDT"

for i in range(3):
    order_payload = {
        "symbol": symbol,
        "side": "BUY",
        "qty": 0.001,
        "source": "api"
    }
    r_ord = requests.post(f"{base_url}/oms/{instance}/orders", headers=headers, json=order_payload)
    print(f"Order {i+1} status:", r_ord.status_code)
    ord_data = r_ord.json()
    mid = ord_data.get("order", {}).get("market_order_id")
    print(f"  Order ID: {mid}, State: {ord_data.get('order', {}).get('state')}")
    if mid:
        market_order_ids.append(mid)
    time.sleep(0.5)

print("\n--- Step 3: Account Funds and Open Positions ---")
r_pos = requests.get(f"{base_url}/oms/{instance}/positions?status=OPEN", headers=headers)
print("Positions status:", r_pos.status_code)
pos_data = r_pos.json()
print("Open positions count:", pos_data.get("count"))
active_mids = [p["market_order_id"] for p in pos_data.get("positions", [])]
print("Active market order IDs:", active_mids)

print("\n--- Step 4: Bulk Close ---")
bulk_payload = {
    "market_order_ids": active_mids
}
r_bulk = requests.post(f"{base_url}/oms/{instance}/positions/bulk/squareoff", headers=headers, json=bulk_payload)
print("Bulk close status:", r_bulk.status_code)
print("Bulk close response:", r_bulk.json())

print("\n--- Step 5: Verify Open Positions Dropped to 0 ---")
r_verify = requests.get(f"{base_url}/oms/{instance}/positions?status=OPEN", headers=headers)
print("Final positions count:", r_verify.json().get("count"))
