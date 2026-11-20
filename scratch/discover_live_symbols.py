"""
Discover which symbols have live feeds and can be traded right now.
Also check existing positions from earlier tests.
"""
import requests, json

BASE_URL = "https://lpadmin.blackfx.com"

s_m = requests.Session()
s_m.post(f"{BASE_URL}/api/auth/login", json={"email": "mamm@mailinator.com", "password": "12345678"})
t = s_m.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
h_m = {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}

# Check existing positions and balance
pos = s_m.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_m).json()
print("Current positions:", len(pos.get("positions", [])))
print("Balance:", pos.get("funds", {}).get("balance"))
print("Equity:", pos.get("funds", {}).get("equity"))

for p in pos.get("positions", []):
    print(f"  Open: {p.get('symbol')} {p.get('side')} qty={p.get('net_qty')} id={p.get('market_order_id')}")

# Try various symbols to find live feed
symbols = ["XAUUSD", "US30", "NAS100", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "NZDUSD",
           "USDCAD", "SP500", "OIL", "ETHUSD", "XAGUSD", "EURGBP", "EURJPY"]

print("\nTesting symbol feeds:")
live_symbols = []
for sym in symbols:
    r = s_m.post(f"{BASE_URL}/v1/oms/real/orders", headers=h_m, json={
        "symbol": sym, "side": "BUY", "quantity": 0.01, "type": "MARKET"
    })
    state = "?"
    err = ""
    try:
        body = r.json()
        order = body.get("order", {})
        state = order.get("state", body.get("state", "?"))
        err = body.get("error", "")
    except:
        err = r.text[:100]
    
    if "stale" in err.lower() or "rejected" in state.upper():
        print(f"  {sym}: STALE/REJECTED")
    elif r.status_code == 200 or state == "OPEN" or state == "FILLED":
        print(f"  {sym}: ✅ LIVE! status={r.status_code} state={state}")
        live_symbols.append(sym)
    else:
        print(f"  {sym}: {r.status_code} {err[:80]}")

print(f"\nLive symbols: {live_symbols}")

# Close any stray positions
time_import = "import time; time.sleep(1)"
all_pos = s_m.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_m).json()
for p in all_pos.get("positions", []):
    mid = p.get("market_order_id") or p.get("id")
    sym = p.get("symbol")
    sq = s_m.post(f"{BASE_URL}/v1/oms/real/positions/{mid}/squareoff", headers=h_m)
    print(f"Closed stray {sym} {mid}: {sq.status_code}")
