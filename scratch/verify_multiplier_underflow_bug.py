import sys, os, time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from test_suite.client import BlackTraderClient

client = BlackTraderClient()
base_url = "https://lpadmin.blackfx.com"
instance = "real"

master_tok = client.get_trader_token("mammaster@mailinator.com", "Test@1234")
f1_tok = client.get_trader_token("mamfollower1@mailinator.com", "Test@1234")

m_headers = {"Authorization": f"Bearer {master_tok}"}
f1_headers = {"Authorization": f"Bearer {f1_tok}"}

rf = client.request_with_retry("GET", f"{base_url}/v1/oms/{instance}/mam/follows", headers=m_headers)
master_cid = rf.json().get("master", {}).get("client_id")

# Set Follower1 to 0.25x multiplier
r_fol = client.request_with_retry("POST", f"{base_url}/v1/oms/{instance}/mam/follow", headers=f1_headers, json={"master_client_id": master_cid, "multiplier": 0.25})
print("Set follower to 0.25x:", r_fol.status_code)

# Master places 0.001 lots
r_open = client.request_with_retry("POST", f"{base_url}/v1/oms/{instance}/orders", headers=m_headers, json={"symbol": "BINANCE:BTCUSDT.P", "side": "BUY", "type": "MARKET", "quantity": 0.001})
mid = r_open.json().get("order", {}).get("market_order_id")
print("Master placed 0.001 lots:", mid)
time.sleep(2)

# Check follower order
r_f1_ord = client.request_with_retry("GET", f"{base_url}/v1/oms/{instance}/orders", headers=f1_headers)
latest = r_f1_ord.json().get("orders", [])[0]
print(f"Follower replicated: requested_qty={latest.get('requested_qty')}, filled_qty={latest.get('filled_qty')}")
print(f"Expected: 0.001 * 0.25 = 0.00025 lots. Actual: {latest.get('filled_qty')} lots (Over-allocation factor: {latest.get('filled_qty') / 0.00025:.1f}x)")

# Close position
if mid:
    client.request_with_retry("POST", f"{base_url}/v1/oms/{instance}/positions/{mid}/squareoff", headers=m_headers)
# Restore multiplier to 2.0
client.request_with_retry("POST", f"{base_url}/v1/oms/{instance}/mam/follow", headers=f1_headers, json={"master_client_id": master_cid, "multiplier": 2.0})

