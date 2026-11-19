from ui_admin_set_balance import admin_set_balance
import requests

BASE_URL = "https://lpadmin.blackfx.com"
r = requests.post(f"{BASE_URL}/admin/api/login", json={"email": "lpadmin@blacktrader.com", "password": "Raj1234!"})
adm_token = r.json().get("token")
adm_headers = {"Authorization": f"Bearer {adm_token}", "Content-Type": "application/json"}

# Restore mamf1 to 10,000
print("Restoring mamf1 to 10,000...")
r1 = requests.post(f"{BASE_URL}/admin/api/members/mem_0ea679062ffd38adf7/balance", 
                   json={"instance": "real", "balance": 10000.0, "force": True}, 
                   headers=adm_headers)
print("mamf1 restore:", r1.json().get("balance"))

# Restore mamf2 to 10,000
print("Restoring mamf2 to 10,000...")
r2 = requests.post(f"{BASE_URL}/admin/api/members/mem_87cc39bb4ddf52a026/balance", 
                   json={"instance": "real", "balance": 10000.0, "force": True}, 
                   headers=adm_headers)
print("mamf2 restore:", r2.json().get("balance"))

# Restore mamf3 to 10,000
print("Restoring mamf3 to 10,000...")
r3 = requests.post(f"{BASE_URL}/admin/api/members/mem_761e39f83d27137624/balance", 
                   json={"instance": "real", "balance": 10000.0, "force": True}, 
                   headers=adm_headers)
print("mamf3 restore:", r3.json().get("balance"))

# Restore Master to 100,000
print("Restoring mamm to 100,000...")
r_m = requests.post(f"{BASE_URL}/admin/api/members/mem_11434b0b9d9d210899/balance", 
                    json={"instance": "real", "balance": 100000.0, "force": True}, 
                    headers=adm_headers)
print("mamm restore:", r_m.json().get("balance"))
