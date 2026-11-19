import sys, os, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from test_suite.client import BlackTraderClient

client = BlackTraderClient()
master_tok = client.get_trader_token("mammaster@mailinator.com", "Test@1234")
headers = {"Authorization": f"Bearer {master_tok}"}

# Test place market order
symbol = "BINANCE:BTCUSDT.P"
order_payload = {
    "symbol": symbol,
    "side": "BUY",
    "type": "MARKET",
    "quantity": 0.001
}

print("Submitting test market order...")
t0 = time.time()
r = client.request_with_retry("POST", "https://lpadmin.blackfx.com/v1/oms/real/orders", headers=headers, json=order_payload)
lat = (time.time() - t0) * 1000
print(f"Order response ({lat:.1f}ms):", r.status_code, r.text)

if r.status_code in [200, 201]:
    res = r.json()
    order_id = res.get("order", {}).get("order_id") or res.get("order_id")
    print(f"Order placed successfully: {order_id}")
    
    time.sleep(2)
    # Check open positions
    r_pos = client.request_with_retry("GET", "https://lpadmin.blackfx.com/v1/oms/real/positions", headers=headers)
    pos_data = r_pos.json()
    print("Open positions count:", pos_data.get("count"))
    
    # Close position
    positions = pos_data.get("positions", [])
    for p in positions:
        mid = p.get("market_order_id")
        if mid:
            print(f"Closing position {mid}...")
            r_close = client.request_with_retry("POST", f"https://lpadmin.blackfx.com/v1/oms/real/positions/{mid}/squareoff", headers=headers)
            print("Close response:", r_close.status_code, r_close.text)

