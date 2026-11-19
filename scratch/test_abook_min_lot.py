import requests

BASE_URL = "https://lpadmin.blackfx.com"
ADMIN_EMAIL = "lpadmin@blacktrader.com"
ADMIN_PASSWORD = "Raj1234!"
FOLLOWER_EMAIL = "mamf1@mailinator.com"
PWD = "12345678"

# 1. Admin switch to A-book
s_adm = requests.Session()
r_adm = s_adm.post(f"{BASE_URL}/admin/api/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
t_adm = r_adm.json().get("token")
h_adm = {"Authorization": f"Bearer {t_adm}", "Content-Type": "application/json"}
s_adm.post(f"{BASE_URL}/admin/api/members/mem_0ea679062ffd38adf7/book", headers=h_adm, json={"book": "a"})

# 2. Trader places 1e-13 order on A-book
s_f = requests.Session()
s_f.post(f"{BASE_URL}/api/auth/login", json={"email": FOLLOWER_EMAIL, "password": PWD})
t_f = s_f.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
h_f = {"Authorization": f"Bearer {t_f}", "Content-Type": "application/json"}

r_ord = s_f.post(f"{BASE_URL}/v1/oms/real/orders", headers=h_f, json={
    "symbol": "BINANCE:BTCUSDT", "side": "BUY", "type": "MARKET", "qty": 1e-13
})
print("A-book 1e-13 BTC order result:", r_ord.status_code, r_ord.text)

# Cleanup
ord_id = r_ord.json().get("order", {}).get("market_order_id")
if ord_id:
    s_f.post(f"{BASE_URL}/v1/oms/real/positions/{ord_id}/squareoff", headers=h_f)

# Reset back to B-book
s_adm.post(f"{BASE_URL}/admin/api/members/mem_0ea679062ffd38adf7/book", headers=h_adm, json={"book": "b"})
