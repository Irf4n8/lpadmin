import requests

BASE_URL = "https://lpadmin.blackfx.com"
s_m = requests.Session()
s_m.post(f"{BASE_URL}/api/auth/login", json={"email": "mamm@mailinator.com", "password": "12345678"})
t_m = s_m.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
h_m = {"Authorization": f"Bearer {t_m}", "Content-Type": "application/json"}

for inst in ["real", "paper"]:
    p_st = s_m.get(f"{BASE_URL}/v1/oms/{inst}/positions", headers=h_m).json()
    for p in p_st.get("positions", []):
        mid = p.get("market_order_id")
        s_m.post(f"{BASE_URL}/v1/oms/{inst}/positions/{mid}/squareoff", headers=h_m)
print("All positions closed.")
