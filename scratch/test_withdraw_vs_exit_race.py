import requests
import json
import concurrent.futures
import time

BASE_URL = "https://lpadmin.blackfx.com"
ADMIN_EMAIL = "lpadmin@blacktrader.com"
ADMIN_PASSWORD = "Raj1234!"
# Use mamf1 (one of the 3 followers)
TEST_EMAIL = "mamf1@mailinator.com"
PWD = "12345678"

# 1. Admin login & prepare
s_adm = requests.Session()
r_adm = s_adm.post(f"{BASE_URL}/admin/api/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
t_adm = r_adm.json().get("token")
h_adm = {"Authorization": f"Bearer {t_adm}", "Content-Type": "application/json"}
m_list = s_adm.get(f"{BASE_URL}/admin/api/members", headers=h_adm).json().get("members", [])
user = next(m for m in m_list if m.get("email") == TEST_EMAIL)
user_id = user.get("member_id")

# Login User
s_u = requests.Session()
s_u.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": PWD})
tok = s_u.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
h_u = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}

print("=" * 75)
print("RACE CONDITION AUDIT: WITHDRAWING / TRANSFERRING OUT VS PLACING EXIT ORDER")
print("=" * 75)

# Step 1: Ensure any wallet balance is transferred back to trading
r_w_init = s_u.get(f"{BASE_URL}/v1/oms/real/wallets", headers=h_u)
w_bal = r_w_init.json().get("wallets", {}).get("client", 0)
if w_bal > 0:
    s_u.post(f"{BASE_URL}/v1/oms/real/wallets/transfer", headers=h_u, json={
        "wallet": "client", "direction": "to_trading", "amount": w_bal
    })

# Set balance to exactly $200.00
s_adm.post(f"{BASE_URL}/admin/api/members/{user_id}/balance", headers=h_adm, json={"instance": "real", "balance": 200.0})

# Step 2: Open a 0.01 BTC BUY position (Margin required is ~$63.60)
r_open = s_u.post(f"{BASE_URL}/v1/oms/real/orders", headers=h_u, json={
    "symbol": "BINANCE:BTCUSDT", "side": "BUY", "type": "MARKET", "qty": 0.01
})
pos_oid = r_open.json().get("order", {}).get("market_order_id")
print(f"Opened Active Trade: {pos_oid}")

time.sleep(1)

# Inspect funds before race
r_funds_b4 = s_u.get(f"{BASE_URL}/v1/oms/real/funds", headers=h_u)
funds_b4 = r_funds_b4.json().get("funds", {})
print(f"Pre-Race Funds: Balance=${funds_b4.get('balance')}, Free Margin=${funds_b4.get('free_margin')}, Used Margin=${funds_b4.get('used_margin')}")

# Step 3: AT THE EXACT SAME MILLISECOND:
# Thread 1: Transfers $180 (most of balance) out to wallet
# Thread 2: Submits squareoff / exit order
def do_transfer_out():
    s = requests.Session()
    return "transfer_out", s.post(f"{BASE_URL}/v1/oms/real/wallets/transfer", headers=h_u, json={
        "wallet": "client", "direction": "to_wallet", "amount": 180.0
    })

def do_exit_order():
    s = requests.Session()
    return "exit_order", s.post(f"{BASE_URL}/v1/oms/real/positions/{pos_oid}/squareoff", headers=h_u)

print("\nFiring simultaneous Transfer-Out ($180) and Exit Order (Square-Off)...")
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
    f_tr = ex.submit(do_transfer_out)
    f_ex = ex.submit(do_exit_order)
    r_tr = f_tr.result()
    r_ex = f_ex.result()

print(f"Transfer-Out Status: {r_tr[1].status_code}, Body: {r_tr[1].text}")
print(f"Exit Order Status: {r_ex[1].status_code}, Body: {r_ex[1].text}")

time.sleep(1)

# Step 4: Audit final balance, equity, and wallet
r_funds_after = s_u.get(f"{BASE_URL}/v1/oms/real/funds", headers=h_u)
r_w_after = s_u.get(f"{BASE_URL}/v1/oms/real/wallets", headers=h_u)
r_pos_after = s_u.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_u)

funds_af = r_funds_after.json().get("funds", {})
wallets_af = r_w_after.json().get("wallets", {})
open_pos_af = r_pos_after.json().get("positions", [])

print("\n" + "=" * 50)
print("POST-RACE FINANCIAL AUDIT:")
print("=" * 50)
print(f"Trading Balance   : ${funds_af.get('balance')}")
print(f"Trading Equity    : ${funds_af.get('equity')}")
print(f"Free Margin       : ${funds_af.get('free_margin')}")
print(f"Client Wallet     : ${wallets_af.get('client')}")
print(f"Total Combined    : ${funds_af.get('balance', 0) + wallets_af.get('client', 0)}")
print(f"Open Positions Rem: {len(open_pos_af)}")

if funds_af.get("balance", 0) < 0:
    print("\n🚨🚨 CRITICAL DEFECT: Trading balance plunged into NEGATIVE territory!")
elif funds_af.get("free_margin", 0) < 0:
    print("\n🚨🚨 CRITICAL DEFECT: Free Margin went NEGATIVE under concurrency!")

# Cleanup: Transfer funds back to trading and reset to $10,000
w_end = wallets_af.get("client", 0)
if w_end > 0:
    s_u.post(f"{BASE_URL}/v1/oms/real/wallets/transfer", headers=h_u, json={
        "wallet": "client", "direction": "to_trading", "amount": w_end
    })
s_adm.post(f"{BASE_URL}/admin/api/members/{user_id}/balance", headers=h_adm, json={"instance": "real", "balance": 10000.0})
print("\nFollower balance restored to $10,000.00.")
