import requests
import json

BASE_URL = "https://lpadmin.blackfx.com"
ADMIN_EMAIL = "lpadmin@blacktrader.com"
ADMIN_PASSWORD = "Raj1234!"
FOLLOWER_EMAIL = "mamf1@mailinator.com"
PWD = "12345678"

# Admin login
adm_s = requests.Session()
adm_s.post(f"{BASE_URL}/admin/api/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "remember": True})
adm_tok = adm_s.post(f"{BASE_URL}/admin/api/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}).json().get("token")
adm_headers = {"Authorization": f"Bearer {adm_tok}", "Content-Type": "application/json"}

# Follower login
f_s = requests.Session()
f_s.post(f"{BASE_URL}/api/auth/login", json={"email": FOLLOWER_EMAIL, "password": PWD})
f_tok = f_s.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
f_headers = {"Authorization": f"Bearer {f_tok}", "Content-Type": "application/json"}

# Test 1: Try deleting default group 'standard'
r_del_grp = adm_s.delete(f"{BASE_URL}/admin/api/groups/standard", headers=adm_headers)
print("Delete default group 'standard':", r_del_grp.status_code, r_del_grp.text)

# Test 2: Create group with negative margin_percent
r_create_grp = adm_s.post(f"{BASE_URL}/admin/api/groups", headers=adm_headers, json={
    "group_code": "negative_margin",
    "name": "Negative Margin Group",
    "margin_percent": -100
})
print("Create group with negative margin_percent:", r_create_grp.status_code, r_create_grp.text)
if r_create_grp.status_code == 200:
    # Cleanup if created
    adm_s.delete(f"{BASE_URL}/admin/api/groups/negative_margin", headers=adm_headers)

# Test 3: Enable/Disable non-existent instance
r_inst_toggle = adm_s.post(f"{BASE_URL}/admin/api/instances/NON_EXISTENT_INSTANCE/enabled", headers=adm_headers, json={"enabled": True})
print("Toggle non-existent instance:", r_inst_toggle.status_code, r_inst_toggle.text)

# Test 4: Rename non-existent instance
r_inst_rename = adm_s.post(f"{BASE_URL}/admin/api/instances/NON_EXISTENT_INSTANCE/name", headers=adm_headers, json={"name": "HackedInstance"})
print("Rename non-existent instance:", r_inst_rename.status_code, r_inst_rename.text)

# Test 5: Member credit grant with amount = 0
r_credit_zero = adm_s.post(f"{BASE_URL}/admin/api/members/mem_0ea679062ffd38adf7/credit", headers=adm_headers, json={
    "instance": "real",
    "amount": 0.0,
    "reason": "Zero Credit Test"
})
print("Grant credit = 0.0:", r_credit_zero.status_code, r_credit_zero.text)

# Test 6: Member KYC review with invalid status
r_kyc_inv = adm_s.post(f"{BASE_URL}/admin/api/kyc/mem_0ea679062ffd38adf7/review", headers=adm_headers, json={
    "status": "APPROVED_WITHOUT_DOCS"
})
print("KYC review with invalid status:", r_kyc_inv.status_code, r_kyc_inv.text)

# Test 7: Trader profile update with XSS payload
r_profile_xss = f_s.post(f"{BASE_URL}/v1/oms/real/portal/profile", headers=f_headers, json={
    "name": "<script>alert('XSS_PROFILE')</script>",
    "phone": "+1234567890",
    "address1": "123 Test Street",
    "city": "London",
    "country": "UK"
})
print("Trader profile update with XSS:", r_profile_xss.status_code, r_profile_xss.text)
# Fetch profile to see if raw script was stored verbatim!
r_prof_get = f_s.get(f"{BASE_URL}/v1/oms/real/portal/summary", headers=f_headers)
print("Fetched profile summary:", r_prof_get.status_code, r_prof_get.text[:300])

# Clean up profile
f_s.post(f"{BASE_URL}/v1/oms/real/portal/profile", headers=f_headers, json={
    "name": "mamf1", "phone": "", "address1": "", "city": "", "country": ""
})

# Test 8: Move money between wallets with negative amount (Client/IB)
r_wallet_neg = f_s.post(f"{BASE_URL}/v1/oms/real/wallets/transfer", headers=f_headers, json={
    "from": "client",
    "to": "real",
    "amount": -500.0
})
print("Move money from client wallet with NEGATIVE amount:", r_wallet_neg.status_code, r_wallet_neg.text)

# Test 9: Move money from client wallet with ZERO amount
r_wallet_zero = f_s.post(f"{BASE_URL}/v1/oms/real/wallets/transfer", headers=f_headers, json={
    "from": "client",
    "to": "real",
    "amount": 0.0
})
print("Move money from client wallet with ZERO amount:", r_wallet_zero.status_code, r_wallet_zero.text)

# Test 10: Move money from client wallet EXCEEDING balance
r_wallet_over = f_s.post(f"{BASE_URL}/v1/oms/real/wallets/transfer", headers=f_headers, json={
    "from": "client",
    "to": "real",
    "amount": 999999999.0
})
print("Move money from client wallet EXCEEDING balance:", r_wallet_over.status_code, r_wallet_over.text)
