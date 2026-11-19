import requests
import json
import concurrent.futures

BASE_URL = "https://lpadmin.blackfx.com"
ADMIN_EMAIL = "lpadmin@blacktrader.com"
ADMIN_PASSWORD = "Raj1234!"
TEST_EMAIL = "mamf95@mailinator.com"
PWD = "12345678"

# 1. Admin login & prepare mamf95
s_adm = requests.Session()
r_adm = s_adm.post(f"{BASE_URL}/admin/api/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
t_adm = r_adm.json().get("token")
h_adm = {"Authorization": f"Bearer {t_adm}", "Content-Type": "application/json"}
m_list = s_adm.get(f"{BASE_URL}/admin/api/members", headers=h_adm).json().get("members", [])
user = next(m for m in m_list if m.get("email") == TEST_EMAIL)
user_id = user.get("member_id")

# Set mamf95 trading balance to exactly $100.00
s_adm.post(f"{BASE_URL}/admin/api/members/{user_id}/balance", headers=h_adm, json={"instance": "real", "balance": 100.0})

# User login
s_u = requests.Session()
s_u.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": PWD})
tok = s_u.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
h_u = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}

print("=" * 70)
print("WALLET TRANSFER TESTS: NEGATIVE AMOUNTS & DOUBLE-SPEND CONCURRENCY")
print("=" * 70)

# Check initial wallets
r_w_init = s_u.get(f"{BASE_URL}/v1/oms/real/wallets", headers=h_u)
print("Initial Wallets:", r_w_init.json().get("totals"))

# TEST 1: Negative Amount Transfer
print("\n--- TEST 1: Negative Amount Transfer (-$50) ---")
r_neg = s_u.post(f"{BASE_URL}/v1/oms/real/wallets/transfer", headers=h_u, json={
    "from": "real",
    "to": "wallet",
    "amount": -50.0
})
print("Negative Transfer Status:", r_neg.status_code, r_neg.text)

# TEST 2: Zero Amount Transfer
print("\n--- TEST 2: Zero Amount Transfer ($0) ---")
r_zero = s_u.post(f"{BASE_URL}/v1/oms/real/wallets/transfer", headers=h_u, json={
    "from": "real",
    "to": "wallet",
    "amount": 0.0
})
print("Zero Transfer Status:", r_zero.status_code, r_zero.text)

# TEST 3: Concurrent Double Transfer Race (Balance = $100.00, Two $80 transfers)
# If both succeed, $160 is transferred out of $100 balance!
print("\n--- TEST 3: Concurrent Transfer Race Condition (2x $80 out of $100) ---")

def do_transfer(tid):
    s = requests.Session()
    return tid, s.post(f"{BASE_URL}/v1/oms/real/wallets/transfer", headers=h_u, json={
        "from": "real",
        "to": "wallet",
        "amount": 80.0
    })

with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
    f1 = ex.submit(do_transfer, 1)
    f2 = ex.submit(do_transfer, 2)
    res1 = f1.result()
    res2 = f2.result()

print(f"Transfer 1 Status: {res1[1].status_code}, Body: {res1[1].text}")
print(f"Transfer 2 Status: {res2[1].status_code}, Body: {res2[1].text}")

# Check final balances
r_w_final = s_u.get(f"{BASE_URL}/v1/oms/real/wallets", headers=h_u)
totals = r_w_final.json().get("totals", {})
print("\nFinal Totals after race:", totals)
print("Trading Balance:", r_w_final.json().get("trading", {}).get("balance"))
print("Client Wallet Balance:", r_w_final.json().get("wallet_details", {}).get("client", {}).get("balance"))

# Reset
s_adm.post(f"{BASE_URL}/admin/api/members/{user_id}/balance", headers=h_adm, json={"instance": "real", "balance": 10000000.0})
print("\nTest completed & balance reset.")
