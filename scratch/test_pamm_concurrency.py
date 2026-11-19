import requests
import json
import concurrent.futures

BASE_URL = "https://lpadmin.blackfx.com"
ADMIN_EMAIL = "lpadmin@blacktrader.com"
ADMIN_PASSWORD = "Raj1234!"
TEST_EMAIL = "mamf94@mailinator.com"
PWD = "12345678"
TARGET_MASTER = "mem_db43041e921ec6db6e" # TM

# Admin setup
s_adm = requests.Session()
r_adm = s_adm.post(f"{BASE_URL}/admin/api/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
t_adm = r_adm.json().get("token")
h_adm = {"Authorization": f"Bearer {t_adm}", "Content-Type": "application/json"}
m_list = s_adm.get(f"{BASE_URL}/admin/api/members", headers=h_adm).json().get("members", [])
user = next(m for m in m_list if m.get("email") == TEST_EMAIL)
user_id = user.get("member_id")

# Set mamf94 balance to $100.00
s_adm.post(f"{BASE_URL}/admin/api/members/{user_id}/balance", headers=h_adm, json={"instance": "real", "balance": 100.0})

# User login
s_u = requests.Session()
s_u.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": PWD})
tok = s_u.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
h_u = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}

print("=" * 70)
print("PAMM JOIN: NEGATIVE, ZERO, & CONCURRENT RACE TESTING")
print("=" * 70)

# Check follows before
r_f_before = s_u.get(f"{BASE_URL}/v1/oms/real/pamm/follows", headers=h_u)
print("Initial PAMM Follows:", r_f_before.json())

# TEST 1: Negative Deposit
print("\n--- TEST 1: PAMM Join with Negative Deposit (-$50) ---")
r_neg = s_u.post(f"{BASE_URL}/v1/oms/real/pamm/join", headers=h_u, json={
    "master_client_id": TARGET_MASTER,
    "deposit": -50.0,
    "operation_key": "op_neg_123"
})
print("Negative Join Status:", r_neg.status_code, r_neg.text)

# TEST 2: Zero Deposit
print("\n--- TEST 2: PAMM Join with Zero Deposit ($0) ---")
r_zero = s_u.post(f"{BASE_URL}/v1/oms/real/pamm/join", headers=h_u, json={
    "master_client_id": TARGET_MASTER,
    "deposit": 0.0,
    "operation_key": "op_zero_123"
})
print("Zero Join Status:", r_zero.status_code, r_zero.text)

# TEST 3: Concurrent PAMM Join Double-Deposit Race
# Balance = $100. Two simultaneous join requests with deposit = $80 each!
print("\n--- TEST 3: Concurrent Double PAMM Join ($80 x 2 out of $100) ---")
def do_join(op_id):
    s = requests.Session()
    return op_id, s.post(f"{BASE_URL}/v1/oms/real/pamm/join", headers=h_u, json={
        "master_client_id": TARGET_MASTER,
        "deposit": 80.0,
        "operation_key": f"op_race_{op_id}"
    })

with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
    j1 = ex.submit(do_join, 1)
    j2 = ex.submit(do_join, 2)
    rj1 = j1.result()
    rj2 = j2.result()

print(f"Join 1 Status: {rj1[1].status_code}, Body: {rj1[1].text}")
print(f"Join 2 Status: {rj2[1].status_code}, Body: {rj2[1].text}")

# Check funds & follows
r_funds_after = s_u.get(f"{BASE_URL}/v1/oms/real/funds", headers=h_u)
r_f_after = s_u.get(f"{BASE_URL}/v1/oms/real/pamm/follows", headers=h_u)
print("Funds after PAMM test:", r_funds_after.json().get("funds"))
print("PAMM Follows after PAMM test:", r_f_after.json())

# Cleanup: unfollow PAMM pool if joined
s_u.post(f"{BASE_URL}/v1/oms/real/pamm/unfollow", headers=h_u, json={
    "master_client_id": TARGET_MASTER,
    "operation_key": "op_unfollow_clean"
})
s_adm.post(f"{BASE_URL}/admin/api/members/{user_id}/balance", headers=h_adm, json={"instance": "real", "balance": 10000000.0})
print("\nCleanup completed.")
