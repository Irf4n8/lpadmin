import requests
import json

BASE_URL = "https://lpadmin.blackfx.com"
r = requests.post(f"{BASE_URL}/admin/api/login", json={"email": "lpadmin@blacktrader.com", "password": "Raj1234!"})
adm_token = r.json().get("token")
adm_headers = {"Authorization": f"Bearer {adm_token}", "Content-Type": "application/json"}

# Try setting balance with force: true
r_force = requests.post(f"{BASE_URL}/admin/api/members/mem_0ea679062ffd38adf7/balance", 
                        json={"instance": "real", "balance": -50.0, "force": True}, 
                        headers=adm_headers)
print("Setting balance with force: true response:", r_force.status_code, r_force.text)

# Check mamf1 funds now
s_f1 = requests.Session()
r_f1 = s_f1.post(f"{BASE_URL}/api/auth/login", json={"email": "mamf1@mailinator.com", "password": "12345678"})
t_f1 = s_f1.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
h_f1 = {"Authorization": f"Bearer {t_f1}", "Content-Type": "application/json"}

state = s_f1.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_f1).json()
print("mamf1 Funds after force:", json.dumps(state.get("funds", {}), indent=2))
print("mamf1 Positions after force:", len(state.get("positions", [])))
