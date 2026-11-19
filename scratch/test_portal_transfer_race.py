import requests
import json
import concurrent.futures

BASE_URL = "https://lpadmin.blackfx.com"
ADMIN_EMAIL = "lpadmin@blacktrader.com"
ADMIN_PASSWORD = "Raj1234!"
TEST_EMAIL = "mamf85@mailinator.com"
PWD = "12345678"

# Admin setup
s_adm = requests.Session()
r_adm = s_adm.post(f"{BASE_URL}/admin/api/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
t_adm = r_adm.json().get("token")
h_adm = {"Authorization": f"Bearer {t_adm}", "Content-Type": "application/json"}
m_list = s_adm.get(f"{BASE_URL}/admin/api/members", headers=h_adm).json().get("members", [])
user = next(m for m in m_list if m.get("email") == TEST_EMAIL)
user_id = user.get("member_id")

# Set mamf85 balance to $200.00
s_adm.post(f"{BASE_URL}/admin/api/members/{user_id}/balance", headers=h_adm, json={"instance": "real", "balance": 200.0})

# User login
s_u = requests.Session()
s_u.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": PWD})
tok = s_u.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
h_u = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}

print("=" * 70)
print("TESTING PORTAL INTERNAL TRANSFERS CONCURRENCY & DOUBLE-SPEND")
print("=" * 70)

# Check initial funds & wallet
r_funds_init = s_u.get(f"{BASE_URL}/v1/oms/real/funds", headers=h_u)
r_wallets_init = s_u.get(f"{BASE_URL}/v1/oms/real/wallets", headers=h_u)
print("Initial Real Funds:", r_funds_init.json().get("funds"))
print("Initial Wallets:", r_wallets_init.json().get("wallets"))

# Fire 2 concurrent transfers of $150 from 'real' to 'wallet' (Balance is only $200!)
def send_portal_transfer(tid):
    s = requests.Session()
    return tid, s.post(f"{BASE_URL}/v1/oms/real/portal/transfers", headers=h_u, json={
        "from": "real",
        "to": "wallet",
        "amount": 150.0
    })

print("\nExecuting 2 concurrent transfers of $80 out of $100...")
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
    t1 = ex.submit(send_portal_transfer, 1)
    t2 = ex.submit(send_portal_transfer, 2)
    res1 = t1.result()
    res2 = t2.result()

print(f"Transfer 1: Status={res1[1].status_code}, Body={res1[1].text}")
print(f"Transfer 2: Status={res2[1].status_code}, Body={res2[1].text}")

# Check final funds & wallet
r_funds_final = s_u.get(f"{BASE_URL}/v1/oms/real/funds", headers=h_u)
r_wallets_final = s_u.get(f"{BASE_URL}/v1/oms/real/wallets", headers=h_u)
print("\nFinal Real Funds:", r_funds_final.json().get("funds"))
print("Final Wallets:", r_wallets_final.json().get("wallets"))

# Cleanup: Transfer back to real and restore balance
w_bal = r_wallets_final.json().get("wallets", {}).get("client", 0)
if w_bal > 0:
    s_u.post(f"{BASE_URL}/v1/oms/real/portal/transfers", headers=h_u, json={
        "from": "wallet", "to": "real", "amount": w_bal
    })
s_adm.post(f"{BASE_URL}/admin/api/members/{user_id}/balance", headers=h_adm, json={"instance": "real", "balance": 10000.0})
print("\nCleanup completed.")
