import requests
import json
import concurrent.futures
import time

BASE_URL = "https://lpadmin.blackfx.com"
ADMIN_EMAIL = "lpadmin@blacktrader.com"
ADMIN_PASSWORD = "Raj1234!"
MASTER_EMAIL = "mamm@mailinator.com"
TEST_EMAIL = "mamf94@mailinator.com"
PWD = "12345678"

# Sessions
s_adm = requests.Session()
r_adm = s_adm.post(f"{BASE_URL}/admin/api/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
t_adm = r_adm.json().get("token")
h_adm = {"Authorization": f"Bearer {t_adm}", "Content-Type": "application/json"}

s_u = requests.Session()
s_u.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": PWD})
tok = s_u.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
h_u = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}

print("=" * 70)
print("CRITICAL PROBE SUITE: MAM FLAPPING, DEPOSIT APPROVAL, & MALFORMED INPUTS")
print("=" * 70)

# -------------------------------------------------------------
# TEST 1: Rapid Follow/Unfollow State Flapping Race Condition
# -------------------------------------------------------------
print("\n--- TEST 1: Concurrent Follow & Unfollow Flapping ---")
master_id = "mem_11434b0b9d9d210899"

def do_follow():
    s = requests.Session()
    return "follow", s.post(f"{BASE_URL}/v1/oms/real/mam/follow", headers=h_u, json={
        "master_client_id": master_id,
        "method": "multiplier",
        "multiplier": 1.5,
        "share_percent": 50.0
    })

def do_unfollow():
    s = requests.Session()
    return "unfollow", s.post(f"{BASE_URL}/v1/oms/real/mam/unfollow", headers=h_u, json={
        "master_client_id": master_id
    })

with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
    f_fol = ex.submit(do_follow)
    f_unf = ex.submit(do_unfollow)
    res_fol = f_fol.result()
    res_unf = f_unf.result()

print(f"Follow Result: Status={res_fol[1].status_code}, Body={res_fol[1].text}")
print(f"Unfollow Result: Status={res_unf[1].status_code}, Body={res_unf[1].text}")

# Check final follows list
r_follows = s_u.get(f"{BASE_URL}/v1/oms/real/mam/follows", headers=h_u)
print("Final Follows Count & States:", [(f.get("follow_id"), f.get("status"), f.get("multiplier")) for f in r_follows.json().get("following", [])])

# -------------------------------------------------------------
# TEST 2: Extreme Floating Point / NaN / Infinity in OMS Orders
# -------------------------------------------------------------
print("\n--- TEST 2: NaN / Infinity / Malformed Float Injection into OMS ---")
malformed_payloads = [
    {"name": "NaN Quantity", "body": {"symbol": "BINANCE:BTCUSDT", "side": "BUY", "type": "MARKET", "qty": float("nan")}},
    {"name": "Infinity Quantity", "body": {"symbol": "BINANCE:BTCUSDT", "side": "BUY", "type": "MARKET", "qty": float("inf")}},
    {"name": "Negative Infinity", "body": {"symbol": "BINANCE:BTCUSDT", "side": "BUY", "type": "MARKET", "qty": float("-inf")}},
    {"name": "Huge Exponent (1e308)", "body": {"symbol": "BINANCE:BTCUSDT", "side": "BUY", "type": "MARKET", "qty": 1e308}},
    {"name": "Negative Quantity (-0.01)", "body": {"symbol": "BINANCE:BTCUSDT", "side": "BUY", "type": "MARKET", "qty": -0.01}},
    {"name": "Zero Quantity (0)", "body": {"symbol": "BINANCE:BTCUSDT", "side": "BUY", "type": "MARKET", "qty": 0}}
]

for p in malformed_payloads:
    try:
        r = s_u.post(f"{BASE_URL}/v1/oms/real/orders", headers=h_u, json=p["body"])
        print(f"[{p['name']}] Status: {r.status_code}, Body: {r.text[:120]}")
    except Exception as e:
        print(f"[{p['name']}] Exception: {e}")

# -------------------------------------------------------------
# TEST 3: Deposit Creation & Double Approval Race Condition
# -------------------------------------------------------------
print("\n--- TEST 3: Portal Deposit Double Review Race Condition ---")
# 1. User creates a deposit request
r_dep_req = s_u.post(f"{BASE_URL}/v1/oms/real/portal/deposits", headers=h_u, json={
    "amount": 500.0,
    "currency": "USDT",
    "tx_hash": "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
})
print("Deposit Request Status:", r_dep_req.status_code, r_dep_req.text)
dep_id = r_dep_req.json().get("deposit_id") or r_dep_req.json().get("deposit", {}).get("id") or r_dep_req.json().get("id")
print("Created Deposit ID:", dep_id)

if dep_id:
    # 2. Fire TWO simultaneous approve requests from Admin
    def approve_dep(req_id):
        s = requests.Session()
        return req_id, s.post(f"{BASE_URL}/admin/api/deposits/{dep_id}/review", headers=h_adm, json={
            "action": "approve",
            "notes": f"Concurrent Approval {req_id}"
        })

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        f_app1 = ex.submit(approve_dep, 1)
        f_app2 = ex.submit(approve_dep, 2)
        r_app1 = f_app1.result()
        r_app2 = f_app2.result()

    print(f"Approval 1: Status={r_app1[1].status_code}, Body={r_app1[1].text}")
    print(f"Approval 2: Status={r_app2[1].status_code}, Body={r_app2[1].text}")

print("\n--- Suite Finished ---")
