import requests
import json

BASE_URL = "https://lpadmin.blackfx.com"
TEST_EMAIL = "mamf93@mailinator.com"
PWD = "12345678"
MASTER_ID = "mem_11434b0b9d9d210899"

s = requests.Session()
s.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": PWD})
tok = s.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}

print("=" * 70)
print("AUDITING MAM SUBSCRIPTION PARAMETERS & EDGE CASES")
print("=" * 70)

test_cases = [
    {"name": "Negative Share Percent (-20%)", "body": {"master_client_id": MASTER_ID, "method": "multiplier", "multiplier": 1.0, "share_percent": -20.0}},
    {"name": "Excessive Share Percent (150%)", "body": {"master_client_id": MASTER_ID, "method": "multiplier", "multiplier": 1.0, "share_percent": 150.0}},
    {"name": "Zero Share Percent (0%)", "body": {"master_client_id": MASTER_ID, "method": "multiplier", "multiplier": 1.0, "share_percent": 0.0}},
    {"name": "Negative Multiplier (-1.0x)", "body": {"master_client_id": MASTER_ID, "method": "multiplier", "multiplier": -1.0, "share_percent": 50.0}},
    {"name": "Zero Multiplier (0x)", "body": {"master_client_id": MASTER_ID, "method": "multiplier", "multiplier": 0.0, "share_percent": 50.0}},
    {"name": "Astronomical Multiplier (1,000,000x)", "body": {"master_client_id": MASTER_ID, "method": "multiplier", "multiplier": 1000000.0, "share_percent": 50.0}},
    {"name": "Infinitesimal Multiplier (1e-15x)", "body": {"master_client_id": MASTER_ID, "method": "multiplier", "multiplier": 1e-15, "share_percent": 50.0}},
    {"name": "Invalid Method ('arbitrage')", "body": {"master_client_id": MASTER_ID, "method": "arbitrage", "multiplier": 1.0, "share_percent": 50.0}},
    {"name": "Self-Follow (Follow Own Member ID)", "body": {"master_client_id": "mem_53c1b20d3d1ade2a20", "method": "multiplier", "multiplier": 1.0, "share_percent": 50.0}}
]

for tc in test_cases:
    # Cleanup before each attempt
    s.post(f"{BASE_URL}/v1/oms/real/mam/unfollow", headers=h, json={"master_client_id": tc["body"]["master_client_id"]})
    r = s.post(f"{BASE_URL}/v1/oms/real/mam/follow", headers=h, json=tc["body"])
    print(f"\n[{tc['name']}] Status: {r.status_code}")
    print(f"Response: {r.text[:180]}")
    if r.status_code == 200:
        print("🚨 ACCEPTED! Checking follow record in OMS...")
        r_list = s.get(f"{BASE_URL}/v1/oms/real/mam/follows", headers=h)
        print("Record:", r_list.json().get("following", [])[-1:])
        s.post(f"{BASE_URL}/v1/oms/real/mam/unfollow", headers=h, json={"master_client_id": tc["body"]["master_client_id"]})

print("\n--- Suite Finished ---")
