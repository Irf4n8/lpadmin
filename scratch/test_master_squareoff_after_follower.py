import requests

BASE_URL = "https://lpadmin.blackfx.com"
s_m = requests.Session()
r_m = s_m.post(f"{BASE_URL}/api/auth/login", json={"email": "mamm@mailinator.com", "password": "12345678"})
t_m = s_m.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
h_m = {"Authorization": f"Bearer {t_m}", "Content-Type": "application/json"}

state_m = s_m.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_m).json()
print("Master open positions:", len(state_m.get("positions", [])))
for p in state_m.get("positions", []):
    print("  Master pos:", p.get("position_id"), p.get("market_order_id"), p.get("symbol"))
    
    # Now let Master squareoff
    mid = p.get("market_order_id")
    print(f"Master squaring off {mid}...")
    r = s_m.post(f"{BASE_URL}/v1/oms/real/positions/{mid}/squareoff", headers=h_m)
    print("Master squareoff result:", r.status_code, r.text)

# Check mamf1, mamf2, mamf3
for f_email in ["mamf1@mailinator.com", "mamf2@mailinator.com", "mamf3@mailinator.com"]:
    s_f = requests.Session()
    s_f.post(f"{BASE_URL}/api/auth/login", json={"email": f_email, "password": "12345678"})
    t_f = s_f.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
    h_f = {"Authorization": f"Bearer {t_f}", "Content-Type": "application/json"}
    st = s_f.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_f).json()
    print(f"{f_email} positions left:", len(st.get("positions", [])))
