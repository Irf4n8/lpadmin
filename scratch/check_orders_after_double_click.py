import requests
import json

BASE_URL = "https://lpadmin.blackfx.com"
s_m = requests.Session()
s_m.post(f"{BASE_URL}/api/auth/login", json={"email": "mamm@mailinator.com", "password": "12345678"})
t_m = s_m.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
h_m = {"Authorization": f"Bearer {t_m}", "Content-Type": "application/json"}

# Check paper positions (the ticket defaulted to Paper)
p_paper = s_m.get(f"{BASE_URL}/v1/oms/paper/positions", headers=h_m).json()
print("Master Paper Positions count:", len(p_paper.get("positions", [])))
for p in p_paper.get("positions", []):
    print("  Paper Pos:", p.get("position_id"), p.get("market_order_id"), p.get("net_qty"), p.get("opened_at"))

# Check real positions
p_real = s_m.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_m).json()
print("\nMaster Real Positions count:", len(p_real.get("positions", [])))
for p in p_real.get("positions", []):
    print("  Real Pos:", p.get("position_id"), p.get("market_order_id"), p.get("net_qty"), p.get("opened_at"))
