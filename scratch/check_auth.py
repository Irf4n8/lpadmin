import requests, json

BASE_URL = "https://lpadmin.blackfx.com"

# Master auth
s_m = requests.Session()
r = s_m.post(f"{BASE_URL}/api/auth/login", json={"email": "mamm@mailinator.com", "password": "12345678"})
print("Master login:", r.status_code)
t = s_m.post(f"{BASE_URL}/api/auth/chart-token").json()
print("Token OK:", "token" in t)
t_m = t.get("token")
h_m = {"Authorization": f"Bearer {t_m}", "Content-Type": "application/json"}

# Check positions + funds
r2 = s_m.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_m)
data = r2.json()
print("Positions:", r2.status_code, json.dumps(data, indent=2)[:500])

# Admin auth
r3 = requests.post(f"{BASE_URL}/admin/api/login", json={"email": "lpadmin@blacktrader.com", "password": "Raj1234!"})
print("Admin login:", r3.status_code)
adm_token = r3.json().get("token")
print("Admin token OK:", bool(adm_token))
