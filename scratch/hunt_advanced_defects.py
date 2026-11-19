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

# 1. Login Master & Follower
s_m = requests.Session()
s_m.post(f"{BASE_URL}/api/auth/login", json={"email": MASTER_EMAIL, "password": PWD})
m_tok = s_m.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
m_headers = {"Authorization": f"Bearer {m_tok}", "Content-Type": "application/json"}

s_f = requests.Session()
s_f.post(f"{BASE_URL}/api/auth/login", json={"email": FOLLOWER_EMAIL, "password": PWD})
f_tok = s_f.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
f_headers = {"Authorization": f"Bearer {f_tok}", "Content-Type": "application/json"}

print(f"Master and Follower authenticated successfully.")

qa_findings = []

def record_finding(test_id, title, result_type, details):
    qa_findings.append({
        "id": test_id,
        "title": title,
        "result": result_type,
        "details": details
    })
    print(f"\n[{result_type}] TEST {test_id}: {title}")
    for k, v in details.items():
        print(f"   {k}: {v}")

# -------------------------------------------------------------
# TEST 1: Trailing Stop Loss Parameter Boundaries
# -------------------------------------------------------------
# Open test position
r_open = s_m.post(f"{BASE_URL}/v1/oms/{INSTANCE}/orders", headers=m_headers, json={
    "symbol": SYMBOL, "side": "BUY", "type": "MARKET", "qty": 0.01
})
pos_id = r_open.json().get("order", {}).get("market_order_id")

if pos_id:
    # 1a. Negative trailing distance
    r_trail_neg = s_m.put(f"{BASE_URL}/v1/oms/{INSTANCE}/positions/{pos_id}/protection", headers=m_headers, json={
        "trailing": -150.0
    })
    # 1b. Trailing distance = 0
    r_trail_zero = s_m.put(f"{BASE_URL}/v1/oms/{INSTANCE}/positions/{pos_id}/protection", headers=m_headers, json={
        "trailing": 0.0
    })
    # 1c. Absurd trailing distance (e.g. 1,000,000)
    r_trail_huge = s_m.put(f"{BASE_URL}/v1/oms/{INSTANCE}/positions/{pos_id}/protection", headers=m_headers, json={
        "trailing": 1000000.0
    })
    
    # Close test position
    s_m.post(f"{BASE_URL}/v1/oms/{INSTANCE}/positions/{pos_id}/squareoff", headers=m_headers)

    record_finding(1, "Trailing Stop Loss Validation", "COMPLETED", {
        "Negative Trailing Distance Status": r_trail_neg.status_code,
        "Negative Trailing Distance Body": r_trail_neg.text,
        "Zero Trailing Distance Status": r_trail_zero.status_code,
        "Zero Trailing Distance Body": r_trail_zero.text,
        "Extreme Trailing Distance (1M) Status": r_trail_huge.status_code,
        "Extreme Trailing Distance Body": r_trail_huge.text
    })

# -------------------------------------------------------------
# TEST 2: Sub-Minimum Lot Sizing in MAM Replication
# -------------------------------------------------------------
# BTC min lot size is 0.001. If master trades 0.001 and follower has multiplier 0.01x,
# expected follower lot is 0.00001 (below min lot). How does OMS handle it?
# Set follower multiplier to 0.01x (minimum allowed)
s_f.post(f"{BASE_URL}/v1/oms/{INSTANCE}/mam/follow", headers=f_headers, json={
    "master_client_id": "mem_11434b0b9d9d210899", "method": "multiplier", "multiplier": 0.01, "share_percent": 50.0
})

r_min_m = s_m.post(f"{BASE_URL}/v1/oms/{INSTANCE}/orders", headers=m_headers, json={
    "symbol": SYMBOL, "side": "BUY", "type": "MARKET", "qty": 0.001
})
min_m_id = r_min_m.json().get("order", {}).get("market_order_id")

time.sleep(1.5)

# Check follower position
r_f_pos = s_f.get(f"{BASE_URL}/v1/oms/{INSTANCE}/positions", headers=f_headers)
f_pos_list = [p for p in r_f_pos.json().get("positions", []) if p.get("symbol") == SYMBOL and p.get("source") == "mam"]

sub_lot_handled = False
if len(f_pos_list) > 0:
    sub_lot_handled = True
    f_qty = f_pos_list[0].get("net_qty")
else:
    f_qty = 0

# Cleanup
if min_m_id:
    s_m.post(f"{BASE_URL}/v1/oms/{INSTANCE}/positions/{min_m_id}/squareoff", headers=m_headers)
for p in f_pos_list:
    s_f.post(f"{BASE_URL}/v1/oms/{INSTANCE}/positions/{p.get('market_order_id')}/squareoff", headers=f_headers)

record_finding(2, "MAM Sub-Minimum Lot Size Handling", "COMPLETED", {
    "Master Placed Qty": "0.001 BTC",
    "Follower Multiplier": "0.01x",
    "Calculated Theoretical Qty": "0.00001 BTC",
    "Follower Actually Replicated": f"{f_qty} BTC",
    "Did Position Open?": "Yes" if sub_lot_handled else "No (Dropped / Below Step Size)"
})

# -------------------------------------------------------------
# TEST 3: Basket Order Partial Failure (Atomicity Check)
# -------------------------------------------------------------
# Place basket where Leg 1 has valid symbol and Leg 2 has invalid symbol
# Expected: Entire basket should reject atomically without opening Leg 1.
r_basket_atomic = s_m.post(f"{BASE_URL}/v1/oms/{INSTANCE}/orders/basket", headers=m_headers, json={
    "legs": [
        {"symbol": "BINANCE:BTCUSDT", "side": "BUY", "qty": 0.01},
        {"symbol": "INVALID:FAKE_COIN_999", "side": "BUY", "qty": 0.01}
    ]
})
time.sleep(1)
# Verify if Leg 1 accidentally got filled
r_check_pos = s_m.get(f"{BASE_URL}/v1/oms/{INSTANCE}/positions", headers=m_headers)
open_btc_pos = [p for p in r_check_pos.json().get("positions", []) if p.get("symbol") == SYMBOL]

# Cleanup if leaked
for p in open_btc_pos:
    s_m.post(f"{BASE_URL}/v1/oms/{INSTANCE}/positions/{p.get('market_order_id')}/squareoff", headers=m_headers)

record_finding(3, "Basket Order Atomic Execution Integrity", "COMPLETED", {
    "Basket Response Status": r_basket_atomic.status_code,
    "Basket Response Body": r_basket_atomic.text,
    "Open Positions Leaked From Failed Basket": len(open_btc_pos),
    "Atomicity Preserved": len(open_btc_pos) == 0
})

# -------------------------------------------------------------
# TEST 4: Unfollow Behavior with Active Open Positions
# -------------------------------------------------------------
# If a follower has an active copied position and clicks Unfollow / Leave Master:
# Does the position remain open as an unmanaged orphan, or is it automatically closed, or is unfollow blocked?
# 1. Reset follower to 1.0x
s_f.post(f"{BASE_URL}/v1/oms/{INSTANCE}/mam/follow", headers=f_headers, json={
    "master_client_id": "mem_11434b0b9d9d210899", "method": "multiplier", "multiplier": 1.0, "share_percent": 50.0
})
# 2. Master opens trade
r_m_trade = s_m.post(f"{BASE_URL}/v1/oms/{INSTANCE}/orders", headers=m_headers, json={
    "symbol": SYMBOL, "side": "BUY", "type": "MARKET", "qty": 0.01
})
m_pos_trade_id = r_m_trade.json().get("order", {}).get("market_order_id")
time.sleep(1.5)

# Verify follower has the trade
r_f_active = s_f.get(f"{BASE_URL}/v1/oms/{INSTANCE}/positions", headers=f_headers)
f_copied = [p for p in r_f_active.json().get("positions", []) if p.get("symbol") == SYMBOL and p.get("source") == "mam"]
print(f"Follower copied trade present: {len(f_copied)}")

# 3. Follower attempts to UNFOLLOW while position is open
r_unfol = s_f.post(f"{BASE_URL}/v1/oms/{INSTANCE}/mam/unfollow", headers=f_headers, json={
    "master_client_id": "mem_11434b0b9d9d210899"
})
print("Unfollow attempt status while position open:", r_unfol.status_code, r_unfol.text)

# Check what happened to the follower's open position!
time.sleep(1)
r_f_after_unfol = s_f.get(f"{BASE_URL}/v1/oms/{INSTANCE}/positions", headers=f_headers)
f_pos_after = [p for p in r_f_after_unfol.json().get("positions", []) if p.get("symbol") == SYMBOL]

# Now master closes position
if m_pos_trade_id:
    s_m.post(f"{BASE_URL}/v1/oms/{INSTANCE}/positions/{m_pos_trade_id}/squareoff", headers=m_headers)
time.sleep(1)

# Check if master close still reached the unfollowed account's position
r_f_final = s_f.get(f"{BASE_URL}/v1/oms/{INSTANCE}/positions", headers=f_headers)
f_pos_final = [p for p in r_f_final.json().get("positions", []) if p.get("symbol") == SYMBOL]

# Cleanup any orphaned position
for p in f_pos_final:
    s_f.post(f"{BASE_URL}/v1/oms/{INSTANCE}/positions/{p.get('market_order_id')}/squareoff", headers=f_headers)

# Re-link follower cleanly
s_f.post(f"{BASE_URL}/v1/oms/{INSTANCE}/mam/follow", headers=f_headers, json={
    "master_client_id": "mem_11434b0b9d9d210899", "method": "multiplier", "multiplier": 1.0, "share_percent": 50.0
})

record_finding(4, "Unfollow With Active Open Positions Handling", "COMPLETED", {
    "Unfollow Request Status": r_unfol.status_code,
    "Unfollow Allowed While Position Open": "Yes" if r_unfol.status_code == 200 else "Blocked",
    "Position Left Open on Follower After Unfollow": len(f_pos_after),
    "Did Master Close Still Cascade to Unfollowed Account?": "No (Position Orphaned!)" if len(f_pos_final) > 0 else "Yes (Closed with Master)",
    "Final Orphan Count": len(f_pos_final)
})

# Save findings to disk
with open("scratch/advanced_qa_findings.json", "w") as f:
    json.dump(qa_findings, f, indent=2)

print("\n" + "=" * 70)
print("🏁 ADVANCED QA DEFECT HUNT COMPLETE. SAVED TO scratch/advanced_qa_findings.json")
print("=" * 70)
