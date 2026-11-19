import requests
import time
import concurrent.futures
from ui_admin_set_balance import admin_set_balance

BASE_URL = "https://lpadmin.blackfx.com"

# Sessions
s_m = requests.Session()
r_m = s_m.post(f"{BASE_URL}/api/auth/login", json={"email": "mamm@mailinator.com", "password": "12345678"})
t_m = s_m.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
h_m = {"Authorization": f"Bearer {t_m}", "Content-Type": "application/json"}

s_f1 = requests.Session()
r_f1 = s_f1.post(f"{BASE_URL}/api/auth/login", json={"email": "mamf1@mailinator.com", "password": "12345678"})
t_f1 = s_f1.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
h_f1 = {"Authorization": f"Bearer {t_f1}", "Content-Type": "application/json"}

# Check mamf1 positions
f1_state = s_f1.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_f1).json()
pos_list = f1_state.get("positions", [])
print(f"mamf1 positions currently open: {len(pos_list)}")

if not pos_list:
    print("Opening a new position on Master...")
    order_payload = {
        "symbol": "BINANCE:BTCUSDT.P",
        "side": "buy",
        "quantity": 0.002,
        "type": "market"
    }
    r_ord = s_m.post(f"{BASE_URL}/v1/oms/real/orders", json=order_payload, headers=h_m)
    time.sleep(2)
    f1_state = s_f1.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_f1).json()
    pos_list = f1_state.get("positions", [])

print(f"mamf1 positions: {len(pos_list)}")
target_pos = pos_list[0]
pos_id = target_pos.get("position_id") or target_pos.get("id")
used_margin = target_pos.get("margin_used") or 25.48
print(f"Target Position: {pos_id}, margin_used: {used_margin}")

print("\n--- INITIATING RACE: Squareoff Position vs Admin Balance Withdrawal to $5.00 ---")
def do_squareoff():
    t0 = time.time()
    r = s_f1.post(f"{BASE_URL}/v1/oms/real/positions/{pos_id}/squareoff", headers=h_f1)
    t1 = time.time()
    return ("squareoff", r.status_code, r.text, round((t1 - t0)*1000, 2))

def do_admin_withdraw():
    t0 = time.time()
    res = admin_set_balance("mamf1@mailinator.com", 5.0, "real", "race_withdraw_during_exit.png")
    t1 = time.time()
    return ("admin_set_bal", 200, res, round((t1 - t0)*1000, 2))

with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
    f_sq = executor.submit(do_squareoff)
    f_wd = executor.submit(do_admin_withdraw)
    
    res_sq = f_sq.result()
    res_wd = f_wd.result()

print(f"Result Squareoff: {res_sq}")
print(f"Result Admin Withdrawal: {res_wd}")

time.sleep(3)
f1_final = s_f1.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_f1).json()
print("\nFinal mamf1 funds after race condition:")
print("  Balance:    ", f1_final.get("funds", {}).get("balance"))
print("  Equity:     ", f1_final.get("funds", {}).get("equity"))
print("  Free Margin:", f1_final.get("funds", {}).get("free_margin"))
print("  Margin Used:", f1_final.get("funds", {}).get("used_margin"))
print("  Remaining Positions:", len(f1_final.get("positions", [])))
