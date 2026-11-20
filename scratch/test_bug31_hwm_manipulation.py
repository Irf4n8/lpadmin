"""
BUG-31: MAM Profit Sharing / HWM Manipulation — 
Attack: 
  1. Set up follower, master trades and gains profit
  2. Admin manually resets balance DOWN (without touching HWM record)
  3. Check if profit share is still calculated on old HWM
  4. Alternatively: Can profit be claimed twice via concurrent requests?
"""
import requests, json, time

BASE_URL = "https://lpadmin.blackfx.com"

def make_session(email, password):
    s = requests.Session()
    s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
    t = s.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
    return s, {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}

s_m, h_m = make_session("mamm@mailinator.com", "12345678")
s_f1, h_f1 = make_session("mamf1@mailinator.com", "12345678")

adm_r = requests.post(f"{BASE_URL}/admin/api/login", json={"email": "lpadmin@blacktrader.com", "password": "Raj1234!"})
adm_token = adm_r.json().get("token")
adm_headers = {"Authorization": f"Bearer {adm_token}", "Content-Type": "application/json"}

MASTER_ID = "mem_11434b0b9d9d210899"
F1_ID = "mem_0ea679062ffd38adf7"

print("=== BUG-31: MAM HWM & Profit Share Manipulation ===\n")

# Check current HWM/shares
shares_r = s_m.get(f"{BASE_URL}/v1/oms/real/mam/shares", headers=h_m)
print(f"Current shares: {shares_r.status_code} {shares_r.text[:500]}")

# Check follow status
follows_r = s_f1.get(f"{BASE_URL}/v1/oms/real/mam/follows", headers=h_f1)
print(f"F1 follows: {follows_r.status_code} {follows_r.text[:300]}")

# Try to retrieve profit share claim endpoint (various common patterns)
claim_endpoints = [
    f"{BASE_URL}/v1/oms/real/mam/claim",
    f"{BASE_URL}/v1/oms/real/mam/withdraw-profit",
    f"{BASE_URL}/v1/oms/real/mam/profit",
    f"{BASE_URL}/v1/oms/real/mam/shares/claim",
    f"{BASE_URL}/v1/oms/real/mam/performance-fee",
]

print("\n--- Profit Claim Endpoint Discovery ---")
for ep in claim_endpoints:
    r = s_m.get(ep, headers=h_m)
    print(f"GET {ep.split('/')[-1]}: {r.status_code} {r.text[:150]}")
    r2 = s_m.post(ep, headers=h_m, json={})
    print(f"POST {ep.split('/')[-1]}: {r2.status_code} {r2.text[:150]}")

# Check if there are any MAM management endpoints
mam_endpoints = [
    f"{BASE_URL}/v1/oms/real/mam",
    f"{BASE_URL}/v1/oms/real/mam/settings",
    f"{BASE_URL}/v1/oms/real/mam/followers",
    f"{BASE_URL}/v1/oms/real/mam/allocation",
    f"{BASE_URL}/v1/oms/real/mam/performance",
]
print("\n--- MAM Endpoint Discovery ---")
for ep in mam_endpoints:
    r = s_m.get(ep, headers=h_m)
    print(f"GET {ep.split('/')[-1]}: {r.status_code} {r.text[:200]}")

print("\nBUG-31 test complete.")
