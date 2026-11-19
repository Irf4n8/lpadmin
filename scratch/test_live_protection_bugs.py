import requests
import json
import concurrent.futures
import time

BASE_URL = "https://lpadmin.blackfx.com"
TEST_EMAIL = "mamf93@mailinator.com"
PWD = "12345678"

s = requests.Session()
s.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": PWD})
tok = s.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}

print("=" * 70)
print("AUDITING LIVE POSITION PROTECTION (SL/TP) INVERSIONS & RACE CONDITIONS")
print("=" * 70)

# Check active position
r_pos = s.get(f"{BASE_URL}/v1/oms/real/positions", headers=h)
positions = r_pos.json().get("positions", [])
if not positions:
    r_open = s.post(f"{BASE_URL}/v1/oms/real/orders", headers=h, json={
        "symbol": "BINANCE:BTCUSDT", "side": "BUY", "type": "MARKET", "qty": 0.01
    })
    pos_oid = r_open.json().get("order", {}).get("market_order_id")
    r_pos = s.get(f"{BASE_URL}/v1/oms/real/positions", headers=h)
    positions = r_pos.json().get("positions", [])
else:
    pos_oid = positions[0].get("market_order_id")

pos_info = positions[0]
avg_price = pos_info.get("avg_entry_price")
side = pos_info.get("side")
print(f"Target Position: {pos_oid}, Side: {side}, Entry Price: {avg_price}")

# -------------------------------------------------------------
# TEST 1: Inverted SL (SL > Market Price on BUY)
# -------------------------------------------------------------
print("\n--- TEST 1: Setting Inverted SL on BUY (SL = $85,000 > Entry ~$63,600) ---")
r_sl_inv = s.put(f"{BASE_URL}/v1/oms/real/positions/{pos_oid}/protection", headers=h, json={
    "sl": 85000.0
})
print("Inverted SL Status:", r_sl_inv.status_code, r_sl_inv.text)

# -------------------------------------------------------------
# TEST 2: Inverted TP (TP < Market Price on BUY)
# -------------------------------------------------------------
print("\n--- TEST 2: Setting Inverted TP on BUY (TP = $40,000 < Entry ~$63,600) ---")
r_tp_inv = s.put(f"{BASE_URL}/v1/oms/real/positions/{pos_oid}/protection", headers=h, json={
    "tp": 40000.0
})
print("Inverted TP Status:", r_tp_inv.status_code, r_tp_inv.text)

# -------------------------------------------------------------
# TEST 3: Negative Price SL / TP
# -------------------------------------------------------------
print("\n--- TEST 3: Setting Negative SL / TP (-$5,000) ---")
r_neg_sl = s.put(f"{BASE_URL}/v1/oms/real/positions/{pos_oid}/protection", headers=h, json={
    "sl": -5000.0
})
print("Negative SL Status:", r_neg_sl.status_code, r_neg_sl.text)

# Check position state after malformed updates
r_pos_check = s.get(f"{BASE_URL}/v1/oms/real/positions", headers=h)
print("Position State in OMS:", r_pos_check.json().get("positions", []))

# -------------------------------------------------------------
# TEST 4: Race Condition: Simultaneous Square-Off vs Protection Update
# -------------------------------------------------------------
print("\n--- TEST 4: Simultaneous Square-Off vs Protection Update Collision ---")
def do_squareoff():
    s_c = requests.Session()
    return "squareoff", s_c.post(f"{BASE_URL}/v1/oms/real/positions/{pos_oid}/squareoff", headers=h)

def do_protect():
    s_p = requests.Session()
    return "protect", s_p.put(f"{BASE_URL}/v1/oms/real/positions/{pos_oid}/protection", headers=h, json={
        "sl": 60000.0, "tp": 70000.0
    })

with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
    f_sq = ex.submit(do_squareoff)
    f_pr = ex.submit(do_protect)
    res_sq = f_sq.result()
    res_pr = f_pr.result()

print(f"Square-off Status: {res_sq[1].status_code}, Body: {res_sq[1].text}")
print(f"Protection Update Status: {res_pr[1].status_code}, Body: {res_pr[1].text}")

time.sleep(1)

# Check if position is closed or if it remained open / ghosted with protection
r_pos_final = s.get(f"{BASE_URL}/v1/oms/real/positions", headers=h)
print("Open Positions Count after Race:", len(r_pos_final.json().get("positions", [])))

print("\n--- Audit Finished ---")
