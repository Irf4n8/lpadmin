import requests

login_url = "https://lpadmin.blackfx.com/v1/oms/_auth/login"
r = requests.post(login_url, json={"email": "mamf1@mailinator.com", "password": "12345678"})
token = r.json()["token"]
headers = {"Authorization": f"Bearer {token}"}

rf = requests.get("https://lpadmin.blackfx.com/v1/oms/real/mam/follows", headers=headers)
print("mamf1 follows:", rf.json())

# Also check admin member account_type for mamf1 and mamm
r_admin_login = requests.post("https://lpadmin.blackfx.com/admin/api/login", json={"email": "lpadmin@blacktrader.com", "password": "Raj1234!", "remember": True})
admin_token = r_admin_login.json().get("token")
r_mem = requests.get("https://lpadmin.blackfx.com/admin/api/members", headers={"Authorization": f"Bearer {admin_token}"})
members = r_mem.json().get("members", [])
mamm_m = next(m for m in members if m.get("email") == "mamm@mailinator.com")
mamf1_m = next(m for m in members if m.get("email") == "mamf1@mailinator.com")
print("mamm account_type:", mamm_m.get("account_type"), "balances:", mamm_m.get("balances"))
print("mamf1 account_type:", mamf1_m.get("account_type"), "balances:", mamf1_m.get("balances"))
