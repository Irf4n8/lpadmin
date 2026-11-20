"""
BUG-24: Negative Quantity Order — Server should reject but might accept
Attack: Submit market order with quantity -1 or 0 to see if the server accepts it.
        Negative quantity could reverse position or cause inventory corruption.
"""
import requests, json

BASE_URL = "https://lpadmin.blackfx.com"

def make_session(email, password):
    s = requests.Session()
    s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
    t = s.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
    return s, {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}

s_m, h_m = make_session("mamm@mailinator.com", "12345678")

test_cases = [
    {"symbol": "EURUSD", "side": "BUY", "quantity": -1, "type": "MARKET"},
    {"symbol": "EURUSD", "side": "BUY", "quantity": 0, "type": "MARKET"},
    {"symbol": "EURUSD", "side": "BUY", "quantity": -0.001, "type": "MARKET"},
    {"symbol": "EURUSD", "side": "SELL", "quantity": -100, "type": "MARKET"},
    {"symbol": "EURUSD", "side": "BUY", "quantity": 999999999, "type": "MARKET"},  # Integer overflow
    {"symbol": "EURUSD", "side": "BUY", "quantity": 1e308, "type": "MARKET"},  # Float overflow
    {"symbol": "EURUSD", "side": "BUY", "quantity": float("inf"), "type": "MARKET"},  # Infinity
    {"symbol": "EURUSD", "side": "BUY", "quantity": float("nan"), "type": "MARKET"},  # NaN
]

print("=== BUG-24: Quantity Boundary / Injection Tests ===\n")
bugs_found = []
for i, tc in enumerate(test_cases):
    try:
        r = s_m.post(f"{BASE_URL}/v1/oms/real/orders", headers=h_m, json=tc)
        status = r.status_code
        body = r.text[:200]
        print(f"[{i+1}] qty={tc['quantity']} side={tc['side']} → {status}: {body}")
        if status == 200:
            bugs_found.append({"test": i+1, "payload": tc, "status": status, "response": body})
    except Exception as e:
        print(f"[{i+1}] Exception: {e}")

print(f"\n=== FINDINGS ===")
if bugs_found:
    for b in bugs_found:
        print(f"🚨 BUG-24 VARIANT: qty={b['payload']['quantity']} returned HTTP 200!")
        print(f"   Response: {b['response']}")
else:
    print("No quantity injection bugs found (server rejected all invalid quantities).")

# Check no phantom positions were created
pos = s_m.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_m).json()
print(f"\nFinal positions: {len(pos.get('positions', []))}")
print(f"Final balance: {pos.get('funds', {}).get('balance')}")

# Clean up any stray positions
for p in pos.get("positions", []):
    mid = p.get("market_order_id") or p.get("id")
    sq = s_m.post(f"{BASE_URL}/v1/oms/real/positions/{mid}/squareoff", headers=h_m)
    print(f"Cleanup: {sq.status_code}")

print("\nBUG-24 test complete.")
