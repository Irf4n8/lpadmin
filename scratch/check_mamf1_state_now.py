import requests

s_f1 = requests.Session()
r_f1 = s_f1.post("https://lpadmin.blackfx.com/api/auth/login", json={"email": "mamf1@mailinator.com", "password": "12345678"})
t_f1 = s_f1.post("https://lpadmin.blackfx.com/api/auth/chart-token").json().get("token")
h_f1 = {"Authorization": f"Bearer {t_f1}", "Content-Type": "application/json"}

state = s_f1.get("https://lpadmin.blackfx.com/v1/oms/real/positions", headers=h_f1).json()
print("mamf1 Funds State:", state.get("funds"))
print("mamf1 Positions:", len(state.get("positions", [])))
for p in state.get("positions", []):
    print("  Position:", p)
