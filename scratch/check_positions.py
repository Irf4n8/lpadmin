import sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from test_suite.client import BlackTraderClient

client = BlackTraderClient()
master_tok = client.get_trader_token("mammaster@mailinator.com", "Test@1234")
headers = {"Authorization": f"Bearer {master_tok}"}

# Check open orders and positions on real
r_pos = client.request_with_retry("GET", "https://lpadmin.blackfx.com/v1/oms/real/positions", headers=headers)
print("Master open positions on real:", r_pos.status_code, r_pos.json() if r_pos.status_code == 200 else r_pos.text)

r_ord = client.request_with_retry("GET", "https://lpadmin.blackfx.com/v1/oms/real/orders", headers=headers)
print("Master open orders on real:", r_ord.status_code, r_ord.json() if r_ord.status_code == 200 else r_ord.text)

