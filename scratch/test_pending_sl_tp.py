import requests

r_login = requests.post("https://lpadmin.blackfx.com/v1/oms/_auth/login", json={
    "email": "mamm@mailinator.com",
    "password": "12345678"
})
token = r_login.json().get("token")
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# Place BUY LIMIT order below market (e.g. at 50,000 when market is ~64,400)
# but with an INVERTED SL above entry price (e.g. SL at 60,000!)
r_pending = requests.post("https://lpadmin.blackfx.com/v1/oms/real/orders/pending", headers=headers, json={
    "symbol": "BINANCE:BTCUSDT",
    "side": "BUY",
    "type": "LIMIT",
    "price": 50000.0,
    "qty": 0.01,
    "sl": 60000.0, # Inverted SL! On a BUY order, SL must be below entry price (50,000), here it is 60,000!
    "tp": 70000.0
})
print("Pending BUY LIMIT with SL > price:", r_pending.status_code, r_pending.text)
ord_id = r_pending.json().get("order", {}).get("order_id")
if ord_id:
    # Cleanup pending order
    requests.delete(f"https://lpadmin.blackfx.com/v1/oms/real/orders/{ord_id}", headers=headers)
