import requests
import json
import concurrent.futures
import time

BASE_URL = "https://lpadmin.blackfx.com"
TEST_EMAIL = "mamf91@mailinator.com"
PWD = "12345678"

s = requests.Session()
s.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": PWD})
tok = s.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}

print("=" * 70)
print("AUDITING POSITION REDUCE: OVER-REDUCE, NEGATIVE, & CONCURRENT RACE")
print("=" * 70)

# Open a 0.01 BTC BUY position
r_open = s.post(f"{BASE_URL}/v1/oms/real/orders", headers=h, json={
    "symbol": "BINANCE:BTCUSDT", "side": "BUY", "type": "MARKET", "qty": 0.01
})
pos_oid = r_open.json().get("order", {}).get("market_order_id")
print("Opened Test Position:", pos_oid)

# TEST 1: Over-Reduce (Reduce 0.05 BTC on a 0.01 BTC position)
print("\n--- TEST 1: Over-Reduce (0.05 BTC on 0.01 BTC Position) ---")
r_over = s.post(f"{BASE_URL}/v1/oms/real/positions/{pos_oid}/reduce", headers=h, json={"qty": 0.05})
print("Over-Reduce Status:", r_over.status_code, r_over.text)

# TEST 2: Negative Reduce (qty = -0.01 BTC)
print("\n--- TEST 2: Negative Reduce (qty = -0.01 BTC) ---")
r_neg = s.post(f"{BASE_URL}/v1/oms/real/positions/{pos_oid}/reduce", headers=h, json={"qty": -0.01})
print("Negative Reduce Status:", r_neg.status_code, r_neg.text)

# Check position state
r_mid = s.get(f"{BASE_URL}/v1/oms/real/positions", headers=h)
positions_mid = [p for p in r_mid.json().get("positions", []) if p.get("market_order_id") == pos_oid]
print("Position State after Tests 1 & 2:", positions_mid[0] if positions_mid else "Closed")

# TEST 3: Concurrent Double Reduce Race Condition
# Open position has 0.01 BTC. Two simultaneous reduce calls for 0.01 BTC each!
# Does one fail, or do both succeed and invert into -0.01 BTC short or double-credit realized PnL?
print("\n--- TEST 3: Concurrent Double Reduce Race (2x 0.01 BTC on 0.01 BTC Position) ---")

def do_reduce(rid):
    s_r = requests.Session()
    return rid, s_r.post(f"{BASE_URL}/v1/oms/real/positions/{pos_oid}/reduce", headers=h, json={"qty": 0.01})

with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
    f1 = ex.submit(do_reduce, 1)
    f2 = ex.submit(do_reduce, 2)
    r1 = f1.result()
    r2 = f2.result()

print(f"Reduce 1: Status={r1[1].status_code}, Body={r1[1].text}")
print(f"Reduce 2: Status={r2[1].status_code}, Body={r2[1].text}")

time.sleep(1)

# Check remaining positions & realized P&L
r_final = s.get(f"{BASE_URL}/v1/oms/real/positions", headers=h)
final_pos = [p for p in r_final.json().get("positions", []) if p.get("symbol") == "BINANCE:BTCUSDT"]
print("\nRemaining Open Positions after Race:", len(final_pos))
for p in final_pos:
    print(f"  Position: ID={p.get('market_order_id')}, Side={p.get('side')}, Qty={p.get('net_qty')}")

# Cleanup
for p in final_pos:
    s.post(f"{BASE_URL}/v1/oms/real/positions/{p.get('market_order_id')}/squareoff", headers=h)
print("\nCleanup completed.")
