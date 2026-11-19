import requests
import json

BASE_URL = "https://lpadmin.blackfx.com"
ADMIN_EMAIL = "lpadmin@blacktrader.com"
ADMIN_PASSWORD = "Raj1234!"
FOLLOWER_EMAIL = "mamf1@mailinator.com"
PWD = "12345678"

# 1. Admin login
adm_s = requests.Session()
adm_s.post(f"{BASE_URL}/admin/api/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "remember": True})
adm_tok = adm_s.post(f"{BASE_URL}/admin/api/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}).json().get("token")
adm_headers = {"Authorization": f"Bearer {adm_tok}", "Content-Type": "application/json"}

# 2. Follower login
f_s = requests.Session()
f_s.post(f"{BASE_URL}/api/auth/login", json={"email": FOLLOWER_EMAIL, "password": PWD})
f_tok = f_s.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
f_headers = {"Authorization": f"Bearer {f_tok}", "Content-Type": "application/json"}
follower_client_id = "mem_0ea679062ffd38adf7"

# Test 1: Self-Referral Loop in IB (Referrer = Self)
r_ib_self = f_s.post(f"{BASE_URL}/v1/oms/real/ib/referrer", headers=f_headers, json={
    "referrer_id": follower_client_id
})
print("IB Self-Referral attempt:", r_ib_self.status_code, r_ib_self.text)

# Test 2: IB Referrer with invalid/non-existent referrer ID
r_ib_bogus = f_s.post(f"{BASE_URL}/v1/oms/real/ib/referrer", headers=f_headers, json={
    "referrer_id": "mem_bogus_fake_id_1234"
})
print("IB Non-Existent Referrer attempt:", r_ib_bogus.status_code, r_ib_bogus.text)

# Test 3: PAMM Join with Negative / Zero Deposit
r_pamm_neg = f_s.post(f"{BASE_URL}/v1/oms/real/pamm/join", headers=f_headers, json={
    "master_client_id": "mem_11434b0b9d9d210899",
    "amount": -5000.0
})
print("PAMM Join with negative deposit:", r_pamm_neg.status_code, r_pamm_neg.text)

r_pamm_zero = f_s.post(f"{BASE_URL}/v1/oms/real/pamm/join", headers=f_headers, json={
    "master_client_id": "mem_11434b0b9d9d210899",
    "amount": 0.0
})
print("PAMM Join with zero deposit:", r_pamm_zero.status_code, r_pamm_zero.text)

# Test 4: Copy Trading Self-Follow Loop
r_copy_self = f_s.post(f"{BASE_URL}/v1/oms/real/copy/follow", headers=f_headers, json={
    "master_client_id": follower_client_id,
    "multiplier": 1.0
})
print("Copy Trading Self-Follow attempt:", r_copy_self.status_code, r_copy_self.text)

# Test 5: Admin Adjust Member AI Credits with Negative Value
r_ai_neg = adm_s.post(f"{BASE_URL}/admin/api/members/{follower_client_id}/ai-credits", headers=adm_headers, json={
    "delta": -999999
})
print("Admin Adjust AI Credits with Negative Delta:", r_ai_neg.status_code, r_ai_neg.text)

# Test 6: AI Assistant Generate called directly
r_ai_gen = f_s.post(f"{BASE_URL}/v1/oms/_ai/generate", headers=f_headers, json={
    "prompt": "Test AI code generation"
})
print("AI Assistant Generate:", r_ai_gen.status_code, r_ai_gen.text[:300])

# Test 7: Admin mint member chart token for non-existent member
r_tok_nonexist = adm_s.post(f"{BASE_URL}/admin/api/members/mem_nonexistent_999/chart-token", headers=adm_headers)
print("Mint chart token for non-existent member:", r_tok_nonexist.status_code, r_tok_nonexist.text)

# Test 8: Admin set member plan for non-existent member
r_plan_nonexist = adm_s.post(f"{BASE_URL}/admin/api/members/mem_nonexistent_999/plan", headers=adm_headers, json={"plan": "free"})
print("Set plan for non-existent member:", r_plan_nonexist.status_code, r_plan_nonexist.text)
