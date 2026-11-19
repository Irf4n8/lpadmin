import requests
import concurrent.futures
import time

BASE_URL = "https://lpadmin.blackfx.com"
MASTER_EMAIL = "mamm@mailinator.com"
PWD = "12345678"
INSTANCE = "real"
SYMBOL = "BINANCE:BTCUSDT"

s_m = requests.Session()
s_m.post(f"{BASE_URL}/api/auth/login", json={"email": MASTER_EMAIL, "password": PWD})
m_tok = s_m.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
m_h = {"Authorization": f"Bearer {m_tok}", "Content-Type": "application/json"}

# Place a pending order
r_pending = s_m.post(f"{BASE_URL}/v1/oms/{INSTANCE}/orders/pending", headers=m_h, json={
    "symbol": SYMBOL,
    "side": "BUY",
    "type": "LIMIT",
    "price": 50000.0,
    "qty": 0.01
})
ord_id = r_pending.json().get("order", {}).get("order_id")
print("Pending order created:", ord_id)

if ord_id:
    # Fire MODIFY and CANCEL simultaneously
    def do_modify():
        return s_m.put(f"{BASE_URL}/v1/oms/{INSTANCE}/orders/{ord_id}/modify", headers=m_h, json={
            "price": 51000.0,
            "qty": 0.02
        })

    def do_cancel():
        return s_m.delete(f"{BASE_URL}/v1/oms/{INSTANCE}/orders/{ord_id}", headers=m_h)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        f_mod = ex.submit(do_modify)
        f_can = ex.submit(do_cancel)
        res_mod = f_mod.result()
        res_can = f_can.result()

    print(f"Modify Response: {res_mod.status_code}, Body: {res_mod.text}")
    print(f"Cancel Response: {res_can.status_code}, Body: {res_can.text}")

    # Check pending orders list to see if the order is still alive or cancelled
    r_orders = s_m.get(f"{BASE_URL}/v1/oms/{INSTANCE}/orders/pending", headers=m_h)
    pending_list = [o for o in r_orders.json().get("orders", []) if o.get("order_id") == ord_id]
    print(f"Order state in pending list: {len(pending_list)}")
    if pending_list:
        print("Order survived race condition:", pending_list[0])
        # cleanup
        s_m.delete(f"{BASE_URL}/v1/oms/{INSTANCE}/orders/{ord_id}", headers=m_h)
    else:
        print("Order successfully terminated without race zombie.")
