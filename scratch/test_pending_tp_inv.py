import requests

r_login = requests.post("https://lpadmin.blackfx.com/v1/oms/_auth/login", json={"email": "mamm@mailinator.com", "password": "12345678"})
token = r_login.json().get("token")
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

r = requests.post("https://lpadmin.blackfx.com/v1/oms/real/orders/pending", headers=headers, json={
    "symbol": "BINANCE:BTCUSDT",
    "side": "BUY",
    "type": "LIMIT",
    "price": 50000.0,
    "qty": 0.01,
    "tp": 40000.0  # Inverted TP on BUY!
})
print("Pending BUY LIMIT with TP < price:", r.status_code, r.text)
ord_id = r.json().get("order", {}).get("order_id")
if ord_id:
    requests.delete(f"https://lpadmin.blackfx.com/v1/oms/real/orders/{ord_id}", headers=headers)
