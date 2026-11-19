import requests
import json
import concurrent.futures
import time

BASE_URL = "https://lpadmin.blackfx.com"
ADMIN_EMAIL = "lpadmin@blacktrader.com"
ADMIN_PASSWORD = "Raj1234!"
TEST_EMAIL = "mamf1@mailinator.com"
PWD = "12345678"

# Admin setup
s_adm = requests.Session()
r_adm = s_adm.post(f"{BASE_URL}/admin/api/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
t_adm = r_adm.json().get("token")
h_adm = {"Authorization": f"Bearer {t_adm}", "Content-Type": "application/json"}
m_list = s_adm.get(f"{BASE_URL}/admin/api/members", headers=h_adm).json().get("members", [])
user = next(m for m in m_list if m.get("email") == TEST_EMAIL)
user_id = user.get("member_id")

# User login
s_u = requests.Session()
s_u.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": PWD})
tok = s_u.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
h_u = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}

print("=" * 75)
print("TESTING DEFICIT EXTRACTION: CAN BALANCE PLUNGE NEGATIVE DURING LOSS EXIT?")
print("=" * 75)

# Reset balance to $100.00
s_adm.post(f"{BASE_URL}/admin/api/members/{user_id}/balance", headers=h_adm, json={"instance": "real", "balance": 100.0})

# Open a 0.01 BTC position
r_open = s_u.post(f"{BASE_URL}/v1/oms/real/orders", headers=h_u, json={
    "symbol": "BINANCE:BTCUSDT", "side": "BUY", "type": "MARKET", "qty": 0.01
})
pos_oid = r_open.json().get("order", {}).get("market_order_id")
print("Position Opened:", pos_oid)

time.sleep(1)

# Check funds: Balance=$100, Free Margin ~$36
r_funds = s_u.get(f"{BASE_URL}/v1/oms/real/funds", headers=h_u)
funds = r_funds.json().get("funds", {})
print("Pre-Race Funds:", funds)

# Transfer $95 out while simultaneously exiting
def do_transfer_out():
    s = requests.Session()
    return "transfer_out", s.post(f"{BASE_URL}/v1/oms/real/wallets/transfer", headers=h_u, json={
        "wallet": "client", "direction": "to_wallet", "amount": 95.0
    })

def do_exit_order():
    s = requests.Session()
    return "exit_order", s.post(f"{BASE_URL}/v1/oms/real/positions/{pos_oid}/squareoff", headers=h_u)

with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
    f_tr = ex.submit(do_transfer_out)
    f_ex = ex.submit(do_exit_order)
    r_tr = f_tr.result()
    r_ex = f_ex.result()

print(f"Transfer-Out: {r_tr[1].status_code}, Body: {r_tr[1].text}")
print(f"Exit Order: {r_ex[1].status_code}, Body: {r_ex[1].text}")

time.sleep(1)

# Audit final funds
r_funds_after = s_u.get(f"{BASE_URL}/v1/oms/real/funds", headers=h_u)
r_w_after = s_u.get(f"{BASE_URL}/v1/oms/real/wallets", headers=h_u)
final_funds = r_funds_after.json().get("funds", {})
final_wallets = r_w_after.json().get("wallets", {})

print("\nFinal Trading Funds:", final_funds)
print("Final Wallets:", final_wallets)

if final_funds.get("balance", 0) < 0:
    print(f"\n🚨🚨 CRITICAL DEFECT CONFIRMED: TRADING BALANCE IS NEGATIVE ({final_funds.get('balance')})! 🚨🚨")
else:
    print(f"\nFinal balance remained non-negative: {final_funds.get('balance')}")

# Cleanup
w_end = final_wallets.get("client", 0)
if w_end > 0:
    s_u.post(f"{BASE_URL}/v1/oms/real/wallets/transfer", headers=h_u, json={
        "wallet": "client", "direction": "to_trading", "amount": w_end
    })
s_adm.post(f"{BASE_URL}/admin/api/members/{user_id}/balance", headers=h_adm, json={"instance": "real", "balance": 10000.0})
print("Restored balance to $10,000.00.")
