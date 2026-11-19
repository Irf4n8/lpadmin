import requests
import json
import time

BASE_URL = "https://lpadmin.blackfx.com"
TEST_EMAIL = "mamf93@mailinator.com"
PWD = "12345678"
MASTER_ID = "mem_11434b0b9d9d210899"

# User login
s = requests.Session()
s.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": PWD})
tok = s.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}

print("=" * 70)
print("DEEP PROBE: DUAL SUBSCRIPTION CONFLICT & OPEN POSITION SL/TP INTEGRITY")
print("=" * 70)

# ----------------------------------------------------------------------
# PROBE 1: Dual Subscription Conflict (MAM + Copy Trading Simultaneous)
# Can a follower subscribe via MAM and Copy Trading to the same master?
# ----------------------------------------------------------------------
print("\n--- PROBE 1: MAM + Copy Trading Dual Subscription ---")

# Follow via MAM
r_mam_fol = s.post(f"{BASE_URL}/v1/oms/real/mam/follow", headers=h, json={
    "master_client_id": MASTER_ID,
    "method": "multiplier",
    "multiplier": 1.0,
    "share_percent": 50.0
})
print("MAM Follow Status:", r_mam_fol.status_code, r_mam_fol.text[:150])

# Now attempt to Follow SAME Master via Copy Trading (/copy/follow)
r_copy_fol = s.post(f"{BASE_URL}/v1/oms/real/copy/follow", headers=h, json={
    "master_client_id": MASTER_ID,
    "method": "multiplier",
    "multiplier": 1.0,
    "share_percent": 50.0
})
print("Copy Follow Status:", r_copy_fol.status_code, r_copy_fol.text[:150])

# Check follows on both
r_mam_list = s.get(f"{BASE_URL}/v1/oms/real/mam/follows", headers=h)
r_copy_list = s.get(f"{BASE_URL}/v1/oms/real/copy/follows", headers=h)
print("MAM Active Subscriptions:", len(r_mam_list.json().get("following", [])))
print("Copy Active Subscriptions:", len(r_copy_list.json().get("following", [])))

# ----------------------------------------------------------------------
# PROBE 2: Open Position SL/TP Inversion & Negative Value Validation
# ----------------------------------------------------------------------
print("\n--- PROBE 2: Live Position SL/TP Inversion & Malformed Values ---")
# 1. Open a BUY position
r_open = s.post(f"{BASE_URL}/v1/oms/real/orders", headers=h, json={
    "symbol": "BINANCE:BTCUSDT",
    "side": "BUY",
    "type": "MARKET",
    "qty": 0.01
})
pos_oid = r_open.json().get("order", {}).get("market_order_id")
print("Position Opened:", pos_oid)

# Fetch current price
r_pos = s.get(f"{BASE_URL}/v1/oms/real/positions", headers=h)
pos_data = next((p for p in r_pos.json().get("positions", []) if p.get("market_order_id") == pos_oid), None)
entry_price = pos_data.get("entry_price") if pos_data else 64000.0
print(f"Position Entry Price: {entry_price}")

# Test 2a: Set SL ABOVE entry price for a BUY (e.g. entry = 64,000, SL = 80,000)
# A BUY order SL above market price is completely inverted (it should trigger instantly as a limit, or be rejected)
print("\nAttempting Inverted SL on BUY (SL > Entry Price):")
r_sl_inv = s.post(f"{BASE_URL}/v1/oms/real/positions/{pos_oid}/sl_tp", headers=h, json={
    "stop_loss": entry_price + 5000.0
})
print("Inverted SL Status:", r_sl_inv.status_code, r_sl_inv.text)

# Test 2b: Set TP BELOW entry price for a BUY (e.g. entry = 64,000, TP = 40,000)
print("\nAttempting Inverted TP on BUY (TP < Entry Price):")
r_tp_inv = s.post(f"{BASE_URL}/v1/oms/real/positions/{pos_oid}/sl_tp", headers=h, json={
    "take_profit": entry_price - 10000.0
})
print("Inverted TP Status:", r_tp_inv.status_code, r_tp_inv.text)

# Test 2c: Set Negative SL (-1000)
print("\nAttempting Negative SL:")
r_neg_sl = s.post(f"{BASE_URL}/v1/oms/real/positions/{pos_oid}/sl_tp", headers=h, json={
    "stop_loss": -1000.0
})
print("Negative SL Status:", r_neg_sl.status_code, r_neg_sl.text)

# Cleanup
if pos_oid:
    s.post(f"{BASE_URL}/v1/oms/real/positions/{pos_oid}/squareoff", headers=h)
s.post(f"{BASE_URL}/v1/oms/real/mam/unfollow", headers=h, json={"master_client_id": MASTER_ID})
s.post(f"{BASE_URL}/v1/oms/real/copy/unfollow", headers=h, json={"master_client_id": MASTER_ID})
print("\nCleanup finished.")
