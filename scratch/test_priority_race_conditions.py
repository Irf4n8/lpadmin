import requests
import json
import time
import concurrent.futures

BASE_URL = "https://lpadmin.blackfx.com"
MASTER_EMAIL = "mamm@mailinator.com"
FOLLOWER_EMAIL = "mamf1@mailinator.com"
PWD = "12345678"
INSTANCE = "real"
SYMBOL = "BINANCE:BTCUSDT"

print("=" * 75)
print("🏁 EXECUTING PRIORITY RACE CONDITION TEST SUITE")
print("=" * 75)

# Authenticate Master & Follower
s_m = requests.Session()
s_m.post(f"{BASE_URL}/api/auth/login", json={"email": MASTER_EMAIL, "password": PWD})
m_tok = s_m.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
m_h = {"Authorization": f"Bearer {m_tok}", "Content-Type": "application/json"}

s_f = requests.Session()
s_f.post(f"{BASE_URL}/api/auth/login", json={"email": FOLLOWER_EMAIL, "password": PWD})
f_tok = s_f.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
f_h = {"Authorization": f"Bearer {f_tok}", "Content-Type": "application/json"}

race_results = []

def record(test_code, name, status, details):
    race_results.append({
        "code": test_code,
        "name": name,
        "status": status,
        "details": details
    })
    print(f"\n[{status}] {test_code}: {name}")
    for k, v in details.items():
        print(f"   {k}: {v}")

# --------------------------------------------------------------------------
# SCENARIO 1: BR07 / NET07 - Multi-Tab / Repeated Simultaneous Position Square-Off
# --------------------------------------------------------------------------
# Can a position be closed twice or cause double-credit / position reversal?
print("\n" + "-" * 60)
print("RUNNING SCENARIO 1: Concurrent Square-Off on Same Position (BR07/NET07)")
print("-" * 60)

# Step 1: Open a position
r_open = s_m.post(f"{BASE_URL}/v1/oms/{INSTANCE}/orders", headers=m_h, json={
    "symbol": SYMBOL, "side": "BUY", "type": "MARKET", "qty": 0.01
})
pos_ord_id = r_open.json().get("order", {}).get("market_order_id")
print(f"Opened Test Position: {pos_ord_id}")

time.sleep(1)

# Step 2: Fire 5 simultaneous squareoff requests concurrently using 5 threads
def close_req(worker_id):
    s = requests.Session()
    return worker_id, s.post(f"{BASE_URL}/v1/oms/{INSTANCE}/positions/{pos_ord_id}/squareoff", headers=m_h, timeout=10)

with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
    futures = [ex.submit(close_req, i) for i in range(5)]
    responses = [f.result() for f in futures]

status_codes = [r[1].status_code for r in responses]
success_responses = [r for r in responses if r[1].status_code == 200 and r[1].json().get("success")]
failure_responses = [r for r in responses if r[1].status_code != 200 or not r[1].json().get("success")]

print(f"Concurrent Close Responses: Statuses={status_codes}")
print(f"Successful Closes: {len(success_responses)}, Rejections: {len(failure_responses)}")

# Check if any position remains, or if position reversed into a SELL!
r_pos_check = s_m.get(f"{BASE_URL}/v1/oms/{INSTANCE}/positions", headers=m_h)
remaining_pos = r_pos_check.json().get("positions", [])

reversed_pos = [p for p in remaining_pos if p.get("symbol") == SYMBOL and p.get("side") == "SELL"]

is_double_closed = len(success_responses) > 1
is_reversed = len(reversed_pos) > 0

record("BR07/NET07", "Simultaneous Position Close Race Condition", "FAIL" if (is_double_closed or is_reversed) else "PASS", {
    "Total Concurrent Close Requests": 5,
    "Successful Close Returns (HTTP 200)": len(success_responses),
    "Properly Rejected Returns": len(failure_responses),
    "Double Close Defect Detected": "YES (CRITICAL BUG!)" if is_double_closed else "No (Properly Serialized)",
    "Position Inverted to Opposite Side": "YES (CRITICAL BUG!)" if is_reversed else "No",
    "Open Positions Remaining": len(remaining_pos)
})

# --------------------------------------------------------------------------
# SCENARIO 2: CP10 - Master Closes Position Simultaneously with Follower Manual Close
# --------------------------------------------------------------------------
print("\n" + "-" * 60)
print("RUNNING SCENARIO 2: Master Square-Off vs Follower Manual Square-Off (CP10)")
print("-" * 60)

# Step 1: Follower follows Master
s_f.post(f"{BASE_URL}/v1/oms/{INSTANCE}/mam/follow", headers=f_h, json={
    "master_client_id": "mem_11434b0b9d9d210899", "method": "multiplier", "multiplier": 1.0, "share_percent": 50.0
})

# Step 2: Master opens position
r_m_open2 = s_m.post(f"{BASE_URL}/v1/oms/{INSTANCE}/orders", headers=m_h, json={
    "symbol": SYMBOL, "side": "BUY", "type": "MARKET", "qty": 0.01
})
m_ord_id2 = r_m_open2.json().get("order", {}).get("market_order_id")
time.sleep(1.5)

# Locate follower copied position ID
r_f_pos2 = s_f.get(f"{BASE_URL}/v1/oms/{INSTANCE}/positions", headers=f_h)
f_copied_pos = next((p for p in r_f_pos2.json().get("positions", []) if p.get("symbol") == SYMBOL and p.get("source") == "mam"), None)
assert f_copied_pos is not None, "Follower copied position was not found!"
f_mkt_id2 = f_copied_pos.get("market_order_id")
print(f"Master Order: {m_ord_id2}, Follower Copied Order: {f_mkt_id2}")

# Step 3: Fire MASTER squareoff and FOLLOWER manual squareoff AT THE EXACT SAME INSTANT
def master_close():
    return "master", s_m.post(f"{BASE_URL}/v1/oms/{INSTANCE}/positions/{m_ord_id2}/squareoff", headers=m_h)

def follower_close():
    return "follower", s_f.post(f"{BASE_URL}/v1/oms/{INSTANCE}/positions/{f_mkt_id2}/squareoff", headers=f_h)

with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
    f_mc = ex.submit(master_close)
    f_fc = ex.submit(follower_close)
    res_m = f_mc.result()
    res_f = f_fc.result()

print(f"Master Close Status: {res_m[1].status_code}, Body: {res_m[1].text[:150]}")
print(f"Follower Close Status: {res_f[1].status_code}, Body: {res_f[1].text[:150]}")

time.sleep(2)

# Step 4: Audit follower position state
r_f_final_audit = s_f.get(f"{BASE_URL}/v1/oms/{INSTANCE}/positions", headers=f_h)
f_remaining = [p for p in r_f_final_audit.json().get("positions", []) if p.get("symbol") == SYMBOL]
f_inverted_sell = [p for p in f_remaining if p.get("side") == "SELL"]

cp10_bug = len(f_inverted_sell) > 0 or len(f_remaining) > 0

record("CP10", "Simultaneous Master Close vs Follower Close Collision", "FAIL" if cp10_bug else "PASS", {
    "Master Squareoff Status": res_m[1].status_code,
    "Follower Squareoff Status": res_f[1].status_code,
    "Did Follower Receive Inverted Trade (SELL)?": "YES (CRITICAL BUG!)" if len(f_inverted_sell) > 0 else "No",
    "Orphaned Residual Positions on Follower": len(f_remaining)
})

# Cleanup if any
for p in f_remaining:
    s_f.post(f"{BASE_URL}/v1/oms/{INSTANCE}/positions/{p.get('market_order_id')}/squareoff", headers=f_h)

# --------------------------------------------------------------------------
# SCENARIO 3: CP04 - Follower Clicks Unfollow Concurrently with Master BUY
# --------------------------------------------------------------------------
print("\n" + "-" * 60)
print("RUNNING SCENARIO 3: Follower Unfollow vs Master BUY Collision (CP04)")
print("-" * 60)

# Follower is active
s_f.post(f"{BASE_URL}/v1/oms/{INSTANCE}/mam/follow", headers=f_h, json={
    "master_client_id": "mem_11434b0b9d9d210899", "method": "multiplier", "multiplier": 1.0, "share_percent": 50.0
})

# Concurrently: Master submits BUY order, Follower submits UNFOLLOW
def fire_master_buy():
    return "master_buy", s_m.post(f"{BASE_URL}/v1/oms/{INSTANCE}/orders", headers=m_h, json={
        "symbol": SYMBOL, "side": "BUY", "type": "MARKET", "qty": 0.01
    })

def fire_follower_unfollow():
    return "follower_unfollow", s_f.post(f"{BASE_URL}/v1/oms/{INSTANCE}/mam/unfollow", headers=f_h, json={
        "master_client_id": "mem_11434b0b9d9d210899"
    })

with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
    f_mb = ex.submit(fire_master_buy)
    f_fu = ex.submit(fire_follower_unfollow)
    r_mb = f_mb.result()
    r_fu = f_fu.result()

print(f"Master Buy Status: {r_mb[1].status_code}, Follower Unfollow Status: {r_fu[1].status_code}")
m_mkt_id3 = r_mb[1].json().get("order", {}).get("market_order_id")

time.sleep(2)

# Check Follower subscription status & positions
r_f_sub = s_f.get(f"{BASE_URL}/v1/oms/{INSTANCE}/mam/follows", headers=f_h)
r_f_pos3 = s_f.get(f"{BASE_URL}/v1/oms/{INSTANCE}/positions", headers=f_h)
f_sub_state = r_f_sub.json().get("following", [{}])[-1].get("status")
f_copied_pos3 = [p for p in r_f_pos3.json().get("positions", []) if p.get("symbol") == SYMBOL and p.get("source") == "mam"]

print(f"Follower Final Subscription Status: {f_sub_state}")
print(f"Follower Open Copied Positions: {len(f_copied_pos3)}")

# Close master position
if m_mkt_id3:
    s_m.post(f"{BASE_URL}/v1/oms/{INSTANCE}/positions/{m_mkt_id3}/squareoff", headers=m_h)
time.sleep(1)

# Check if follower copied trade was orphaned or closed
r_f_pos3_after = s_f.get(f"{BASE_URL}/v1/oms/{INSTANCE}/positions", headers=f_h)
f_orphaned = [p for p in r_f_pos3_after.json().get("positions", []) if p.get("symbol") == SYMBOL and p.get("source") == "mam"]

record("CP04", "Unfollow vs Master BUY Collision", "FAIL" if len(f_orphaned) > 0 else "PASS", {
    "Subscription Status after Collision": f_sub_state,
    "Did Trade Copy During Unfollow?": "Yes" if len(f_copied_pos3) > 0 else "No",
    "Did Orphaned Position Remain After Master Closed?": "YES (CRITICAL BUG!)" if len(f_orphaned) > 0 else "No",
    "Residual Orphaned Positions": len(f_orphaned)
})

for p in f_orphaned:
    s_f.post(f"{BASE_URL}/v1/oms/{INSTANCE}/positions/{p.get('market_order_id')}/squareoff", headers=f_h)

# --------------------------------------------------------------------------
# SCENARIO 4: NET01 / BR01 - Multi-Click Duplicate Order Submission
# --------------------------------------------------------------------------
print("\n" + "-" * 60)
print("RUNNING SCENARIO 4: Rapid Multi-Click Duplicate BUY Submission (NET01/BR01)")
print("-" * 60)

# Simulate rapid double-click (2 requests fired at the exact same millisecond)
def rapid_buy(click_id):
    s = requests.Session()
    return click_id, s.post(f"{BASE_URL}/v1/oms/{INSTANCE}/orders", headers=m_h, json={
        "symbol": SYMBOL, "side": "BUY", "type": "MARKET", "qty": 0.01,
        "client_order_id": "CLIENT_REQ_UNIQUE_HASH_12345"  # Testing client idempotency key support
    })

with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
    futures = [ex.submit(rapid_buy, i) for i in range(2)]
    click_res = [f.result() for f in futures]

print(f"Click 1 Status: {click_res[0][1].status_code}, Order ID: {click_res[0][1].json().get('order', {}).get('order_id')}")
print(f"Click 2 Status: {click_res[1][1].status_code}, Order ID: {click_res[1][1].json().get('order', {}).get('order_id')}")

both_filled = (click_res[0][1].status_code == 200 and click_res[1][1].status_code == 200)

time.sleep(1)

# Cleanup open orders
for r in click_res:
    oid = r[1].json().get("order", {}).get("market_order_id")
    if oid:
        s_m.post(f"{BASE_URL}/v1/oms/{INSTANCE}/positions/{oid}/squareoff", headers=m_h)

record("NET01/BR01", "Rapid Double-Click Idempotency Verification", "FAIL" if both_filled else "PASS", {
    "Click 1 Order ID": click_res[0][1].json().get('order', {}).get('order_id'),
    "Click 2 Order ID": click_res[1][1].json().get('order', {}).get('order_id'),
    "Duplicate Orders Executed from One Intent": "YES (Lacks Idempotency Protection)" if both_filled else "No (Deduplicated)",
    "Idempotency Key Respected": not both_filled
})

# Re-link follower cleanly
s_f.post(f"{BASE_URL}/v1/oms/{INSTANCE}/mam/follow", headers=f_h, json={
    "master_client_id": "mem_11434b0b9d9d210899", "method": "multiplier", "multiplier": 1.0, "share_percent": 50.0
})

with open("scratch/race_condition_test_results.json", "w") as f:
    json.dump(race_results, f, indent=2)

print("\n" + "=" * 75)
print("🏁 RACE CONDITION TEST RUN COMPLETE. SAVED TO scratch/race_condition_test_results.json")
print("=" * 75)
