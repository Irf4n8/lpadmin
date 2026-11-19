import requests
import concurrent.futures
import time

BASE_URL = "https://lpadmin.blackfx.com"
ADMIN_EMAIL = "lpadmin@blacktrader.com"
ADMIN_PASSWORD = "Raj1234!"
FOLLOWER_EMAIL = "mamf98@mailinator.com"
PWD = "12345678"
SYMBOL = "BINANCE:BTCUSDT"

# 1. Admin login & get member_id
s_adm = requests.Session()
r_adm = s_adm.post(f"{BASE_URL}/admin/api/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
t_adm = r_adm.json().get("token")
h_adm = {"Authorization": f"Bearer {t_adm}", "Content-Type": "application/json"}
m_list = s_adm.get(f"{BASE_URL}/admin/api/members", headers=h_adm).json().get("members", [])
f98 = next((m for m in m_list if m.get("email") == FOLLOWER_EMAIL), None)
f98_id = f98.get("member_id")

# 2. Set f98 balance to exactly $100 on REAL
# Margin for 0.01 BTC at ~64,200 is ~$64.20.
# So $100 is enough for ONE 0.01 BTC order ($64.20), but NOT enough for TWO ($128.40)!
s_adm.post(f"{BASE_URL}/admin/api/members/{f98_id}/balance", headers=h_adm, json={"instance": "real", "balance": 100.0})

# Follower login
s_f = requests.Session()
s_f.post(f"{BASE_URL}/api/auth/login", json={"email": FOLLOWER_EMAIL, "password": PWD})
t_f = s_f.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
h_f = {"Authorization": f"Bearer {t_f}", "Content-Type": "application/json"}

# Verify funds
r_funds = s_f.get(f"{BASE_URL}/v1/oms/real/funds", headers=h_f)
print("Initial Balance / Free Margin:", r_funds.json().get("funds", {}).get("free_margin"))

# 3. Send 5 simultaneous orders in parallel!
def send_order(idx):
    return s_f.post(f"{BASE_URL}/v1/oms/real/orders", headers=h_f, json={
        "symbol": SYMBOL,
        "side": "BUY",
        "type": "MARKET",
        "qty": 0.01
    }, timeout=10)

print("Launching 5 concurrent market orders...")
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
    futures = [executor.submit(send_order, i) for i in range(5)]
    results = [f.result() for f in futures]

status_codes = [r.status_code for r in results]
filled_count = sum(1 for r in results if r.status_code == 200 and r.json().get("success"))
rejected_count = sum(1 for r in results if r.status_code == 400 or not r.json().get("success"))

print(f"Results: {status_codes}")
print(f"Total Filled: {filled_count}, Total Rejected (Margin): {rejected_count}")

# Check final funds and open positions
r_final_funds = s_f.get(f"{BASE_URL}/v1/oms/real/funds", headers=h_f)
r_final_pos = s_f.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_f)
final_positions = r_final_pos.json().get("positions", [])
print("Final Free Margin:", r_final_funds.json().get("funds", {}).get("free_margin"))
print("Final Open Positions Count:", len(final_positions))

# Cleanup open positions & restore balance to 10,000,000
for p in final_positions:
    s_f.post(f"{BASE_URL}/v1/oms/real/positions/{p.get('market_order_id')}/squareoff", headers=h_f)
s_adm.post(f"{BASE_URL}/admin/api/members/{f98_id}/balance", headers=h_adm, json={"instance": "real", "balance": 10000000.0})
print("Cleanup complete.")
