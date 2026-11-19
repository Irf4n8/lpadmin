import requests

login_url = "https://lpadmin.blackfx.com/v1/oms/_auth/login"
r = requests.post(login_url, json={"email": "mamf1@mailinator.com", "password": "12345678"})
token = r.json()["token"]
headers = {"Authorization": f"Bearer {token}"}

r_orders = requests.get("https://lpadmin.blackfx.com/v1/oms/real/orders", headers=headers)
orders = r_orders.json().get("orders", [])
print(f"mamf1 order count: {len(orders)}")
for o in orders[:4]:
    print(o.get("order_id"), o.get("side"), o.get("state"), o.get("requested_qty"), o.get("copy_kind"), o.get("copy_ref"))

r_pos = requests.get("https://lpadmin.blackfx.com/v1/oms/real/positions?status=OPEN", headers=headers)
print("mamf1 open positions:", r_pos.json().get("count"))
