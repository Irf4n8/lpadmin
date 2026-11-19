import sys, os, time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from test_suite.client import BlackTraderClient

client = BlackTraderClient()
base_url = "https://lpadmin.blackfx.com"
instance = "real"

admin_tok = client.get_admin_token()
master_tok = client.get_trader_token("mammaster@mailinator.com", "Test@1234")
f2_tok = client.get_trader_token("mamfollower2@mailinator.com", "Test@1234")

m_headers = {"Authorization": f"Bearer {master_tok}"}
f2_headers = {"Authorization": f"Bearer {f2_tok}"}

members = client.get_admin_members()
f2 = next(m for m in members if m.get("email") == "mamfollower2@mailinator.com")
f2_id = f2["member_id"]

# Set balance to $0.00
client.set_member_balance(f2_id, 0.0, instance=instance)
funds = client.request_with_retry("GET", f"{base_url}/v1/oms/{instance}/funds", headers=f2_headers).json().get("funds", {})
print("Follower2 initial funds:", funds)

# Check initial positions count
pos_before = client.request_with_retry("GET", f"{base_url}/v1/oms/{instance}/positions", headers=f2_headers).json().get("positions", [])
print("Follower2 positions before master trade:", len(pos_before))

# Master opens trade
print("Master opening 0.001 BUY...")
r_m = client.request_with_retry("POST", f"{base_url}/v1/oms/{instance}/orders", headers=m_headers, json={"symbol": "BINANCE:BTCUSDT.P", "side": "BUY", "type": "MARKET", "quantity": 0.001})
mid = r_m.json().get("order", {}).get("market_order_id")
print("Master order:", mid)
time.sleep(2)

# Check Follower2 positions NOW
pos_after = client.request_with_retry("GET", f"{base_url}/v1/oms/{instance}/positions", headers=f2_headers).json().get("positions", [])
print("Follower2 positions AFTER master trade:", len(pos_after))
if pos_after:
    print("Follower2 position details:", pos_after[0])
    print("Follower2 funds after position open:", client.request_with_retry("GET", f"{base_url}/v1/oms/{instance}/funds", headers=f2_headers).json().get("funds", {}))

# Cleanup
if mid:
    client.request_with_retry("POST", f"{base_url}/v1/oms/{instance}/positions/{mid}/squareoff", headers=m_headers)
client.set_member_balance(f2_id, 10000000, instance=instance)

