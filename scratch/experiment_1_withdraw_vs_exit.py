import requests
import time
import concurrent.futures
import json
import os
from ui_admin_set_balance import admin_set_balance

BASE_URL = "https://lpadmin.blackfx.com"
SCREENSHOT_DIR = os.path.abspath("reports/screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

# 1. Setup Sessions
s_m = requests.Session()
r_m = s_m.post(f"{BASE_URL}/api/auth/login", json={"email": "mamm@mailinator.com", "password": "12345678"})
t_m = s_m.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
h_m = {"Authorization": f"Bearer {t_m}", "Content-Type": "application/json"}

s_f1 = requests.Session()
r_f1 = s_f1.post(f"{BASE_URL}/api/auth/login", json={"email": "mamf1@mailinator.com", "password": "12345678"})
t_f1 = s_f1.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
h_f1 = {"Authorization": f"Bearer {t_f1}", "Content-Type": "application/json"}

print("======================================================================")
print("EXPERIMENT 1: EXIT ORDER VS. ADMIN BALANCE WITHDRAWAL CONCURRENCY RACE")
print("======================================================================")

# Step A: Admin UI sets mamf1 balance to $100.00
print("\n[Step A] Setting mamf1 real balance to $100.00 via Admin UI...")
admin_set_balance("mamf1@mailinator.com", 100.0, "real", "exp1_admin_bal100.png")

# Step B: Master places an order
print("\n[Step B] Master places BUY Market Order for 0.001 BTCUSDT.P...")
ord_res = s_m.post(f"{BASE_URL}/v1/oms/real/orders", json={
    "symbol": "BINANCE:BTCUSDT.P",
    "side": "buy",
    "quantity": 0.001,
    "type": "market"
}, headers=h_m).json()
print("Master Order Created:", ord_res.get("order", {}).get("order_id"))
time.sleep(2)

# Step C: Inspect mamf1 replicated position
f1_state = s_f1.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_f1).json()
f1_positions = f1_state.get("positions", [])
f1_funds = f1_state.get("funds", {})
print(f"mamf1 replicated positions: {len(f1_positions)}")
print("mamf1 Funds during active trade:", json.dumps(f1_funds, indent=2))

if f1_positions:
    f1_pos = f1_positions[0]
    market_order_id = f1_pos.get("market_order_id")
    used_margin = f1_pos.get("margin_used")
    print(f"Active Position market_order_id: {market_order_id}, used_margin: ${used_margin}")
    
    # Step D: Concurrently fire Square-off and Admin balance withdrawal to $0.00
    print("\n[Step D] Launching concurrent Square-Off and Admin UI Balance Withdrawal to $0.00...")
    
    race_results = {}
    
    def task_squareoff():
        t0 = time.time()
        r = s_f1.post(f"{BASE_URL}/v1/oms/real/positions/{market_order_id}/squareoff", headers=h_f1)
        latency = round((time.time() - t0) * 1000, 2)
        race_results["squareoff"] = {
            "status": r.status_code,
            "response": r.json() if r.status_code == 200 else r.text,
            "latency_ms": latency
        }
        
    def task_admin_withdraw():
        t0 = time.time()
        # Admin UI directly modifies balance via API or UI
        # Let's call the Admin API directly for nanosecond concurrency, while also capturing UI screenshot
        # Admin endpoint is POST /admin/api/members/{id}/balance
        r = requests.post(f"{BASE_URL}/admin/api/login", json={"email": "lpadmin@blacktrader.com", "password": "Raj1234!"})
        adm_token = r.json().get("token")
        adm_headers = {"Authorization": f"Bearer {adm_token}", "Content-Type": "application/json"}
        
        # Withdraw balance to 0
        r_bal = requests.post(f"{BASE_URL}/admin/api/members/mem_0ea679062ffd38adf7/balance", 
                              json={"instance": "real", "balance": 0.0}, 
                              headers=adm_headers)
        latency = round((time.time() - t0) * 1000, 2)
        race_results["admin_withdraw"] = {
            "status": r_bal.status_code,
            "response": r_bal.json() if r_bal.status_code == 200 else r_bal.text,
            "latency_ms": latency
        }
        
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        f1 = ex.submit(task_squareoff)
        f2 = ex.submit(task_admin_withdraw)
        concurrent.futures.wait([f1, f2])
        
    print("\n[Step E] Concurrent Race Execution Results:")
    print(json.dumps(race_results, indent=2))
    
    time.sleep(2)
    f1_after = s_f1.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_f1).json()
    print("\n[Step F] Follower State After Race Condition:")
    print("  Funds:", json.dumps(f1_after.get("funds", {}), indent=2))
    print("  Remaining Positions:", len(f1_after.get("positions", [])))

    # Close master position if still open
    m_state = s_m.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_m).json()
    for p in m_state.get("positions", []):
        s_m.post(f"{BASE_URL}/v1/oms/real/positions/{p['market_order_id']}/squareoff", headers=h_m)
