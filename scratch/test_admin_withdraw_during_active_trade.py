import requests
import time
import json
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

print("=========================================================================")
print("EXPERIMENT 2: ADMIN WITHDRAWAL TO ZERO WHILE ACTIVE TRADE IS RUNNING")
print("=========================================================================")

# Step 1: Admin sets mamf1 balance to $100 via Admin UI
print("[Step 1] Setting mamf1 real balance to $100.00 via Admin UI...")
admin_set_balance("mamf1@mailinator.com", 100.0, "real", "exp2_initial_bal100.png")

# Step 2: Master opens position
print("[Step 2] Master opens BUY 0.001 BTCUSDT.P...")
ord_res = s_m.post(f"{BASE_URL}/v1/oms/real/orders", json={
    "symbol": "BINANCE:BTCUSDT.P",
    "side": "buy",
    "quantity": 0.001,
    "type": "market"
}, headers=h_m).json()
time.sleep(2)

# Step 3: Check follower position & used margin
f1_state = s_f1.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_f1).json()
print("mamf1 open positions:", len(f1_state.get("positions", [])))
print("mamf1 Funds before withdrawal:", json.dumps(f1_state.get("funds", {}), indent=2))

# Step 4: Admin UI forces balance to $0 (Withdrawal of entire balance while trade is running)
print("\n[Step 4] Executing Admin UI balance withdrawal to $0 while trade is active...")
admin_set_balance("mamf1@mailinator.com", 0.0, "real", "exp2_zero_bal_active_trade.png")

time.sleep(2)
# Step 5: Check follower state now
f1_after = s_f1.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_f1).json()
print("\n[Step 5] mamf1 Funds AFTER Admin Withdrawal to $0 with active position:")
print(json.dumps(f1_after.get("funds", {}), indent=2))
print("mamf1 Positions count:", len(f1_after.get("positions", [])))

# Step 6: Close master position
m_state = s_m.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_m).json()
for p in m_state.get("positions", []):
    s_m.post(f"{BASE_URL}/v1/oms/real/positions/{p['market_order_id']}/squareoff", headers=h_m)
time.sleep(2)

# Step 7: Final balance after close
f1_close = s_f1.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_f1).json()
print("\n[Step 7] mamf1 Funds AFTER closing the trade that had $0 balance:")
print(json.dumps(f1_close.get("funds", {}), indent=2))
