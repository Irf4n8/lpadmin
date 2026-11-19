import requests
import json
import time

BASE_URL = "https://lpadmin.blackfx.com"
TEST_EMAIL = "mamf88@mailinator.com"
PWD = "12345678"

s = requests.Session()
s.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": PWD})
tok = s.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}

print("=" * 70)
print("AUDITING PENDING ORDER PRICING INTEGRITY & CROSSED BOOK ANOMALIES")
print("=" * 70)

# Check current BTC price
r_price = s.get(f"{BASE_URL}/v1/oms/real/positions", headers=h)
# Place a BUY LIMIT at $95,000 (Current price is ~$63,500)
print("Placing BUY LIMIT at $95,000 (Crossed limit order far above market)...")
r_pending = s.post(f"{BASE_URL}/v1/oms/real/orders/pending", headers=h, json={
    "symbol": "BINANCE:BTCUSDT",
    "side": "BUY",
    "type": "LIMIT",
    "price": 95000.0,
    "qty": 0.01
})
print("BUY LIMIT Status:", r_pending.status_code)
print("BUY LIMIT Body:", r_pending.text)

ord_id = r_pending.json().get("order", {}).get("order_id")

time.sleep(2)

# Check pending orders list
r_pend_list = s.get(f"{BASE_URL}/v1/oms/real/orders/pending", headers=h)
print("\nPending Orders in Book:", [(o.get("order_id"), o.get("price"), o.get("state")) for o in r_pend_list.json().get("orders", []) if o.get("order_id") == ord_id])

# Check open positions (did it fill immediately at $95,000 or at market?)
r_pos = s.get(f"{BASE_URL}/v1/oms/real/positions", headers=h)
pos = next((p for p in r_pos.json().get("positions", []) if p.get("symbol") == "BINANCE:BTCUSDT"), None)
if pos:
    print("\n🚨 ORDER WAS FILLED!")
    print(f"  Entry Price: ${pos.get('avg_entry_price')}")
    print(f"  Current Market Price: ${pos.get('current_price')}")
    print(f"  Unrealized PnL: ${pos.get('unrealized_pnl')}")
    if pos.get('avg_entry_price') >= 90000:
        print("🚨🚨 CRITICAL FINANCIAL DEFECT: BUY LIMIT filled at crossed price $95,000 instead of best market ask!")
        print("   Trader suffered immediate massive unrealized loss due to lack of price crossing / matching protection!")
    # cleanup position
    s.post(f"{BASE_URL}/v1/oms/real/positions/{pos.get('market_order_id')}/squareoff", headers=h)
else:
    print("Order remained pending in book at $95,000 (Resting above market price!).")
    # cleanup pending
    if ord_id:
        s.delete(f"{BASE_URL}/v1/oms/real/orders/{ord_id}", headers=h)

print("\nAudit completed.")
