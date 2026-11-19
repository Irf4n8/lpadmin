import sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from test_suite.client import BlackTraderClient

client = BlackTraderClient()
f_tok = client.get_trader_token("mamfollower1@mailinator.com", "Test@1234")
headers = {"Authorization": f"Bearer {f_tok}"}

r_orders = client.request_with_retry("GET", "https://lpadmin.blackfx.com/v1/oms/real/orders", headers=headers)
orders = r_orders.json().get("orders", [])
print(f"mamfollower1 order count: {len(orders)}")
for o in orders[:5]:
    print(o.get("order_id"), o.get("side"), o.get("state"), o.get("requested_qty"), o.get("filled_qty"), o.get("copy_kind"), o.get("copy_ref"), o.get("created_at"))

