import requests
import json

BASE_URL = "https://lpadmin.blackfx.com"
ADMIN_EMAIL = "lpadmin@blacktrader.com"
ADMIN_PASSWORD = "Raj1234!"
FOLLOWER_EMAIL = "mamf1@mailinator.com"
MASTER_EMAIL = "mamm@mailinator.com"
PWD = "12345678"

# 1. Admin login
adm_s = requests.Session()
adm_s.post(f"{BASE_URL}/admin/api/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "remember": True})
adm_tok = adm_s.post(f"{BASE_URL}/admin/api/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}).json().get("token")
adm_headers = {"Authorization": f"Bearer {adm_tok}", "Content-Type": "application/json"}

# 2. Master login
m_s = requests.Session()
m_s.post(f"{BASE_URL}/api/auth/login", json={"email": MASTER_EMAIL, "password": PWD})
m_tok = m_s.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
m_headers = {"Authorization": f"Bearer {m_tok}", "Content-Type": "application/json"}

# 3. Follower login
f_s = requests.Session()
f_s.post(f"{BASE_URL}/api/auth/login", json={"email": FOLLOWER_EMAIL, "password": PWD})
f_tok = f_s.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
f_headers = {"Authorization": f"Bearer {f_tok}", "Content-Type": "application/json"}
follower_client_id = "mem_0ea679062ffd38adf7"

# Test 1: Follower accessing Master's private MAM Shares breakdown via ?role=master
r_shares_idor = f_s.get(f"{BASE_URL}/v1/oms/real/mam/shares?role=master", headers=f_headers)
print("Follower queries /mam/shares?role=master:", r_shares_idor.status_code, r_shares_idor.text[:300])

# Test 2: Chart admin listPublished called with Trader token
r_chart_admin = f_s.post(f"{BASE_URL}/v1/chart/admin/listPublished", headers=f_headers, json={})
print("Trader calls /v1/chart/admin/listPublished:", r_chart_admin.status_code, r_chart_admin.text[:300])

# Test 3: Chart admin listPublished called with NO token (Unauthenticated)
r_chart_unauth = requests.post(f"{BASE_URL}/v1/chart/admin/listPublished", headers={"Content-Type": "application/json"}, json={})
print("Unauthenticated calls /v1/chart/admin/listPublished:", r_chart_unauth.status_code, r_chart_unauth.text[:300])

# Test 4: Admin sets member password to blank / 1 character
r_pwd_blank = adm_s.post(f"{BASE_URL}/admin/api/members/{follower_client_id}/password", headers=adm_headers, json={"password": ""})
print("Admin sets blank password:", r_pwd_blank.status_code, r_pwd_blank.text)

r_pwd_short = adm_s.post(f"{BASE_URL}/admin/api/members/{follower_client_id}/password", headers=adm_headers, json={"password": "1"})
print("Admin sets 1-char password ('1'):", r_pwd_short.status_code, r_pwd_short.text)
# Reset password back to 12345678
adm_s.post(f"{BASE_URL}/admin/api/members/{follower_client_id}/password", headers=adm_headers, json={"password": "12345678"})

# Test 5: Admin sets invalid member plan (e.g. plan: "UNLIMITED_FREE_MONEY_PLAN")
r_plan = adm_s.post(f"{BASE_URL}/admin/api/members/{follower_client_id}/plan", headers=adm_headers, json={"plan": "UNLIMITED_FREE_MONEY_PLAN"})
print("Admin sets arbitrary plan:", r_plan.status_code, r_plan.text)

# Test 6: Trader unarchives non-existent account
r_unarch = adm_s.post(f"{BASE_URL}/admin/api/accounts/acc_9999999999999/unarchive", headers=adm_headers)
print("Unarchive non-existent account:", r_unarch.status_code, r_unarch.text)

# Test 7: Money operation query with non-existent ID
r_money_op = adm_s.get(f"{BASE_URL}/admin/api/money/operations/op_nonexistent_123", headers=adm_headers)
print("Money operation query non-existent ID:", r_money_op.status_code, r_money_op.text)

# Test 8: Bulk squareoff with 0 IDs (Empty array)
r_bulk_empty = f_s.post(f"{BASE_URL}/v1/oms/real/positions/bulk/squareoff", headers=f_headers, json={"market_order_ids": []})
print("Bulk squareoff with empty array:", r_bulk_empty.status_code, r_bulk_empty.text)

# Test 9: Bulk squareoff with market_order_ids as string instead of array (Crash / 500 test)
r_bulk_str = f_s.post(f"{BASE_URL}/v1/oms/real/positions/bulk/squareoff", headers=f_headers, json={"market_order_ids": "not_an_array"})
print("Bulk squareoff with string instead of array:", r_bulk_str.status_code, r_bulk_str.text)

# Test 10: Position reduce with qty = 0
r_pos_reduce_zero = f_s.post(f"{BASE_URL}/v1/oms/real/positions/some_order_id/reduce", headers=f_headers, json={"qty": 0.0})
print("Position reduce with qty = 0:", r_pos_reduce_zero.status_code, r_pos_reduce_zero.text)
