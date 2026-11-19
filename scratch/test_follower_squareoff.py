import requests

BASE_URL = "https://lpadmin.blackfx.com"
s_f1 = requests.Session()
r_f1 = s_f1.post(f"{BASE_URL}/api/auth/login", json={"email": "mamf1@mailinator.com", "password": "12345678"})
t_f1 = s_f1.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
h_f1 = {"Authorization": f"Bearer {t_f1}", "Content-Type": "application/json"}

state = s_f1.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_f1).json()
positions = state.get("positions", [])
print(f"mamf1 open positions: {len(positions)}")
for p in positions:
    mid = p.get("market_order_id")
    pid = p.get("position_id")
    print(f"Trying squareoff with market_order_id: {mid}")
    r = s_f1.post(f"{BASE_URL}/v1/oms/real/positions/{mid}/squareoff", headers=h_f1)
    print("Squareoff with market_order_id response:", r.status_code, r.text)
    if r.status_code != 200:
        print(f"Trying squareoff with position_id: {pid}")
        r2 = s_f1.post(f"{BASE_URL}/v1/oms/real/positions/{pid}/squareoff", headers=h_f1)
        print("Squareoff with position_id response:", r2.status_code, r2.text)
