import requests, time

base_url = "https://lpadmin.blackfx.com/v1"

# Login mamm
r_m = requests.post(f"{base_url}/oms/_auth/login", json={"email": "mamm@mailinator.com", "password": "12345678"})
m_token = r_m.json()["token"]
m_headers = {"Authorization": f"Bearer {m_token}"}

# Login mamf1
r_f = requests.post(f"{base_url}/oms/_auth/login", json={"email": "mamf1@mailinator.com", "password": "12345678"})
f_token = r_f.json()["token"]
f_headers = {"Authorization": f"Bearer {f_token}"}

# Master places trade
print("Master placing order...")
r_ord = requests.post(f"{base_url}/oms/real/orders", headers=m_headers, json={"symbol": "BINANCE:BTCUSDT", "side": "BUY", "qty": 0.001, "source": "api"})
mid = r_ord.json().get("order", {}).get("market_order_id")
print("Master order:", mid)
time.sleep(2)

# Check mamf1 open positions
r_f_pos = requests.get(f"{base_url}/oms/real/positions?status=OPEN", headers=f_headers)
pos = r_f_pos.json().get("positions", [])
print(f"mamf1 open positions count: {len(pos)}")
if pos:
    print("mamf1 replicated position:", pos[0].get("market_order_id"), pos[0].get("net_qty"), pos[0].get("side"))

# Master closes trade
if mid:
    r_close = requests.post(f"{base_url}/oms/real/positions/{mid}/squareoff", headers=m_headers)
    print("Master close status:", r_close.status_code)
    time.sleep(2)
    # Check mamf1 closed
    r_f_pos2 = requests.get(f"{base_url}/oms/real/positions?status=OPEN", headers=f_headers)
    print("mamf1 open positions after master close:", r_f_pos2.json().get("count"))
