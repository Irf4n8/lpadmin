import requests
import concurrent.futures
import time

BASE_URL = "https://lpadmin.blackfx.com"
s_m = requests.Session()
s_m.post(f"{BASE_URL}/api/auth/login", json={"email": "mamm@mailinator.com", "password": "12345678"})
t_m = s_m.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
h_m = {"Authorization": f"Bearer {t_m}", "Content-Type": "application/json"}

# Payload representing identical order submitted simultaneously from two tabs (BR01 / NET01)
order_payload = {
    "symbol": "BINANCE:BTCUSDT.P",
    "side": "buy",
    "quantity": 0.001,
    "type": "market",
    "client_order_id": "test_idempotency_12345"
}

def place_order(tab_name):
    t0 = time.time()
    r = s_m.post(f"{BASE_URL}/v1/oms/real/orders", json=order_payload, headers=h_m)
    latency = round((time.time() - t0)*1000, 2)
    return tab_name, r.status_code, r.json() if r.status_code == 200 else r.text, latency

print("Submitting identical order from two simulated tabs simultaneously...")
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
    f1 = ex.submit(place_order, "Tab_Chrome")
    f2 = ex.submit(place_order, "Tab_Edge")
    r1 = f1.result()
    r2 = f2.result()

print(f"Result Tab 1: {r1}")
print(f"Result Tab 2: {r2}")

# Check if both created orders despite identical client_order_id
time.sleep(2)
positions = s_m.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_m).json().get("positions", [])
print(f"Total open real positions: {len(positions)}")
for p in positions:
    print(f"  Pos: {p.get('position_id')}, order: {p.get('market_order_id')}, qty: {p.get('net_qty')}")
