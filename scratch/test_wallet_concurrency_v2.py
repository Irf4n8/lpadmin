import requests
import json
import concurrent.futures
import time

BASE_URL = "https://lpadmin.blackfx.com"
ADMIN_EMAIL = "lpadmin@blacktrader.com"
ADMIN_PASSWORD = "Raj1234!"
TEST_EMAIL = "mamf95@mailinator.com"
PWD = "12345678"

# 1. Admin login & prepare mamf95
s_adm = requests.Session()
r_adm = s_adm.post(f"{BASE_URL}/admin/api/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
t_adm = r_adm.json().get("token")
h_adm = {"Authorization": f"Bearer {t_adm}", "Content-Type": "application/json"}
m_list = s_adm.get(f"{BASE_URL}/admin/api/members", headers=h_adm).json().get("members", [])
user = next(m for m in m_list if m.get("email") == TEST_EMAIL)
user_id = user.get("member_id")

# User login
s_u = requests.Session()
s_u.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": PWD})
tok = s_u.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
h_u = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}

# Move any existing wallet balance back to trading
r_w_start = s_u.get(f"{BASE_URL}/v1/oms/real/wallets", headers=h_u)
client_bal = r_w_start.json().get("wallets", {}).get("client", 0)
if client_bal > 0:
    s_u.post(f"{BASE_URL}/v1/oms/real/wallets/transfer", headers=h_u, json={
        "wallet": "client", "direction": "to_trading", "amount": client_bal
    })

# Set mamf95 trading balance to exactly $100.00
s_adm.post(f"{BASE_URL}/admin/api/members/{user_id}/balance", headers=h_adm, json={"instance": "real", "balance": 100.0})

print("=" * 70)
print("WALLET TRANSFER TESTS: NEGATIVE, ZERO, & DOUBLE-SPEND CONCURRENCY")
print("=" * 70)

# TEST 1: Negative Amount Transfer
print("\n--- TEST 1: Negative Amount Transfer (-$50) ---")
r_neg = s_u.post(f"{BASE_URL}/v1/oms/real/wallets/transfer", headers=h_u, json={
    "wallet": "client",
    "direction": "to_wallet",
    "amount": -50.0
})
print("Negative Transfer Status:", r_neg.status_code, r_neg.text)

# TEST 2: Zero Amount Transfer
print("\n--- TEST 2: Zero Amount Transfer ($0) ---")
r_zero = s_u.post(f"{BASE_URL}/v1/oms/real/wallets/transfer", headers=h_u, json={
    "wallet": "client",
    "direction": "to_wallet",
    "amount": 0.0
})
print("Zero Transfer Status:", r_zero.status_code, r_zero.text)

# TEST 3: Concurrent Double Transfer Race (Balance = $100.00, Two $80 transfers)
print("\n--- TEST 3: Concurrent Double Transfer Race (2x $80 out of $100) ---")

def do_transfer(tid):
    s = requests.Session()
    return tid, s.post(f"{BASE_URL}/v1/oms/real/wallets/transfer", headers=h_u, json={
        "wallet": "client",
        "direction": "to_wallet",
        "amount": 80.0
    })

with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
    f1 = ex.submit(do_transfer, 1)
    f2 = ex.submit(do_transfer, 2)
    res1 = f1.result()
    res2 = f2.result()

print(f"Transfer 1 Status: {res1[1].status_code}, Body: {res1[1].text}")
print(f"Transfer 2 Status: {res2[1].status_code}, Body: {res2[1].text}")

# Check final balances
r_w_final = s_u.get(f"{BASE_URL}/v1/oms/real/wallets", headers=h_u)
totals = r_w_final.json().get("totals", {})
print("\nFinal Totals after race:", totals)
print("Trading Balance:", r_w_final.json().get("trading", {}).get("balance"))
print("Client Wallet Balance:", r_w_final.json().get("wallets", {}).get("client"))

# TEST 4: Transfer vs Open Trade Margin (Checking Balance vs Free Margin)
print("\n--- TEST 4: Transfer Out while Position Uses Margin ---")
# Reset balance to $100
# First transfer back to trading
r_w_curr = s_u.get(f"{BASE_URL}/v1/oms/real/wallets", headers=h_u)
w_bal = r_w_curr.json().get("wallets", {}).get("client", 0)
if w_bal > 0:
    s_u.post(f"{BASE_URL}/v1/oms/real/wallets/transfer", headers=h_u, json={
        "wallet": "client", "direction": "to_trading", "amount": w_bal
    })
s_adm.post(f"{BASE_URL}/admin/api/members/{user_id}/balance", headers=h_adm, json={"instance": "real", "balance": 100.0})

# Open a 0.01 BTC BUY position (requires ~$64.30 margin)
r_pos_open = s_u.post(f"{BASE_URL}/v1/oms/real/orders", headers=h_u, json={
    "symbol": "BINANCE:BTCUSDT", "side": "BUY", "type": "MARKET", "qty": 0.01
})
print("Position Opened:", r_pos_open.status_code)
pos_oid = r_pos_open.json().get("order", {}).get("market_order_id")

# Check funds: Balance should be ~$100, Free Margin ~$35
r_funds_mid = s_u.get(f"{BASE_URL}/v1/oms/real/funds", headers=h_u)
funds_mid = r_funds_mid.json().get("funds", {})
print(f"Current Balance: ${funds_mid.get('balance')}, Free Margin: ${funds_mid.get('free_margin')}, Used Margin: ${funds_mid.get('used_margin')}")

# Try to transfer $80 to wallet (More than Free Margin $35, but less than Balance $100!)
# If the server checks Balance instead of Free Margin, this will succeed and plunge Free Margin into negative!
r_over_tr = s_u.post(f"{BASE_URL}/v1/oms/real/wallets/transfer", headers=h_u, json={
    "wallet": "client",
    "direction": "to_wallet",
    "amount": 80.0
})
print("Over-transfer Status:", r_over_tr.status_code, r_over_tr.text)

r_funds_after = s_u.get(f"{BASE_URL}/v1/oms/real/funds", headers=h_u)
print("Funds after transfer attempt:", r_funds_after.json().get("funds"))

# Cleanup
if pos_oid:
    s_u.post(f"{BASE_URL}/v1/oms/real/positions/{pos_oid}/squareoff", headers=h_u)
r_w_clean = s_u.get(f"{BASE_URL}/v1/oms/real/wallets", headers=h_u)
w_clean_bal = r_w_clean.json().get("wallets", {}).get("client", 0)
if w_clean_bal > 0:
    s_u.post(f"{BASE_URL}/v1/oms/real/wallets/transfer", headers=h_u, json={
        "wallet": "client", "direction": "to_trading", "amount": w_clean_bal
    })
s_adm.post(f"{BASE_URL}/admin/api/members/{user_id}/balance", headers=h_adm, json={"instance": "real", "balance": 10000000.0})
print("\nAll cleanups completed.")
