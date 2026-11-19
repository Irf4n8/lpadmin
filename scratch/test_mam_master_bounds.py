import requests
import json

BASE_URL = "https://lpadmin.blackfx.com"
MASTER_EMAIL = "mamm@mailinator.com"
TEST_USER = "mamf87@mailinator.com"
PWD = "12345678"

# Regular Follower Login
s_u = requests.Session()
s_u.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_USER, "password": PWD})
tok_u = s_u.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
h_u = {"Authorization": f"Bearer {tok_u}", "Content-Type": "application/json"}

# Master Login
s_m = requests.Session()
s_m.post(f"{BASE_URL}/api/auth/login", json={"email": MASTER_EMAIL, "password": PWD})
tok_m = s_m.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
h_m = {"Authorization": f"Bearer {tok_m}", "Content-Type": "application/json"}

print("=" * 70)
print("AUDITING MAM MASTER REGISTRATION & PROFIT SHARE BOUNDS")
print("=" * 70)

# TEST 1: Can an arbitrary regular trader register as a MAM Master directly?
print("\n--- TEST 1: Unauthorized MAM Master Self-Elevation ---")
r_elevate = s_u.post(f"{BASE_URL}/v1/oms/real/mam/master", headers=h_u, json={
    "client_id": "mem_arbitrary_self_elevate",
    "display_name": "Rogue Master Account",
    "share_percent": 50,
    "status": "active"
})
print("Self-Elevation Status:", r_elevate.status_code)
print("Self-Elevation Response:", r_elevate.text)

# TEST 2: Can Master set Negative Profit Share (-50%)?
print("\n--- TEST 2: Setting Negative Profit Share (-50%) ---")
r_neg = s_m.post(f"{BASE_URL}/v1/oms/real/mam/master", headers=h_m, json={
    "display_name": "Negative Fee Master",
    "share_percent": -50.0,
    "status": "active"
})
print("Negative Share Status:", r_neg.status_code)
print("Negative Share Response:", r_neg.text)

# TEST 3: Can Master set Excessive Profit Share (150%)?
print("\n--- TEST 3: Setting Excessive Profit Share (150%) ---")
r_over = s_m.post(f"{BASE_URL}/v1/oms/real/mam/master", headers=h_m, json={
    "display_name": "Greedy Master",
    "share_percent": 150.0,
    "status": "active"
})
print("Excessive Share Status:", r_over.status_code)
print("Excessive Share Response:", r_over.text)

# TEST 4: Can Master set 0% Profit Share?
print("\n--- TEST 4: Setting 0% Profit Share ---")
r_zero = s_m.post(f"{BASE_URL}/v1/oms/real/mam/master", headers=h_m, json={
    "display_name": "Zero Fee Master",
    "share_percent": 0.0,
    "status": "active"
})
print("Zero Share Status:", r_zero.status_code)
print("Zero Share Response:", r_zero.text)

# Restore master to normal
s_m.post(f"{BASE_URL}/v1/oms/real/mam/master", headers=h_m, json={
    "display_name": "mammaster",
    "share_percent": 50.0,
    "status": "active"
})

print("\nAudit completed.")
