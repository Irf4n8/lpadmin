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

def run_test(category, title, method, url, headers, payload=None, params=None):
    print(f"\n[{category}] -> {title}")
    print(f"  {method} {url}")
    if payload:
        print(f"  Payload: {json.dumps(payload)}")
    try:
        r = requests.request(method, url, headers=headers, json=payload, params=params, timeout=12)
        print(f"  Status: {r.status_code}")
        print(f"  Response: {r.text[:400]}")
        item = {
            "category": category,
            "title": title,
            "method": method,
            "url": url,
            "payload": payload,
            "status": r.status_code,
            "response": r.text
        }
        results.append(item)
        return r
    except Exception as e:
        print(f"  Exception: {e}")
        return None

# --- BUG TEST 1: Negative Wallet Transfer (Inverse Fund Siphoning) ---
run_test("Wallets", "Transfer Negative Amount from Real to Wallet",
         "POST", f"{BASE_URL}/v1/oms/real/wallets/transfer", follower_headers,
         payload={"from": "real", "to": "wallet", "amount": -500.0})

run_test("Wallets", "Transfer Zero Amount from Real to Wallet",
         "POST", f"{BASE_URL}/v1/oms/real/wallets/transfer", follower_headers,
         payload={"from": "real", "to": "wallet", "amount": 0.0})

# --- BUG TEST 2: Portal Transfers with Negative / Arbitrary Amount ---
run_test("Portal", "Internal Transfer with Negative Amount",
         "POST", f"{BASE_URL}/v1/oms/real/portal/transfers", follower_headers,
         payload={"from": "real", "to": "wallet", "amount": -1000.0})

# --- BUG TEST 3: Portal Withdrawal OTP with Negative / Zero Amount ---
run_test("Withdrawals", "Withdrawal OTP Request with Negative Amount",
         "POST", f"{BASE_URL}/v1/oms/real/portal/withdrawals/otp", follower_headers,
         payload={"amount": -500.0, "method_id": "dummy_method"})

run_test("Withdrawals", "Withdrawal OTP Request with Zero Amount",
         "POST", f"{BASE_URL}/v1/oms/real/portal/withdrawals/otp", follower_headers,
         payload={"amount": 0.0, "method_id": "dummy_method"})

# --- BUG TEST 4: Basket Orders with Negative Leg Qty or Zero Qty ---
run_test("Orders", "Basket Entry with Negative Leg Qty",
         "POST", f"{BASE_URL}/v1/oms/real/orders/basket", master_headers,
         payload={
             "legs": [
                 {"symbol": "BINANCE:BTCUSDT", "side": "BUY", "qty": -0.01}
             ]
         })

run_test("Orders", "Basket Entry with Empty Legs Array",
         "POST", f"{BASE_URL}/v1/oms/real/orders/basket", master_headers,
         payload={"legs": []})

# --- BUG TEST 5: Position Protection: Inverted SL / TP logic ---
# Place test position first
r_open = m_s.post(f"{BASE_URL}/v1/oms/real/orders", headers=master_headers, json={
    "symbol": "BINANCE:BTCUSDT", "side": "BUY", "type": "MARKET", "qty": 0.01
})
pos_ord_id = r_open.json().get("order", {}).get("market_order_id")

if pos_ord_id:
    # Set Inverted Take Profit on BUY: TP = $1.00 (Current BTC is ~64,400)
    run_test("Protection", "Inverted Take-Profit on BUY (tp = 1.0)",
             "PUT", f"{BASE_URL}/v1/oms/real/positions/{pos_ord_id}/protection", master_headers,
             payload={"tp": 1.0, "sl": 0.0})

    # Set Inverted Stop Loss on BUY: SL = $500,000.00 (Current BTC is ~64,400)
    run_test("Protection", "Inverted Stop-Loss on BUY (sl = 500000.0)",
             "PUT", f"{BASE_URL}/v1/oms/real/positions/{pos_ord_id}/protection", master_headers,
             payload={"sl": 500000.0, "tp": 0.0})

    # Set Negative SL / TP
    run_test("Protection", "Negative SL and TP values",
             "PUT", f"{BASE_URL}/v1/oms/real/positions/{pos_ord_id}/protection", master_headers,
             payload={"sl": -500.0, "tp": -100.0})

    # Close test position
    m_s.post(f"{BASE_URL}/v1/oms/real/positions/{pos_ord_id}/squareoff", headers=master_headers)

# --- BUG TEST 6: Admin Member Account-Type Mutation with Invalid Value ---
run_test("Admin", "Set Invalid Member Account Type ('super_admin_tier')",
         "POST", f"{BASE_URL}/admin/api/members/{follower_client_id}/account-type", admin_headers,
         payload={"account_type": "super_admin_tier"})

# --- BUG TEST 7: Admin Credit with Invalid/Zero/Negative Amount ---
run_test("Admin", "Grant Zero Credit via Admin API",
         "POST", f"{BASE_URL}/admin/api/members/{follower_client_id}/credit", admin_headers,
         payload={"instance": "real", "amount": 0.0, "reason": "Zero test"})

# --- BUG TEST 8: Admin Review Non-Existent Deposit (500 crash test) ---
run_test("Admin", "Review Non-Existent Deposit ID",
         "POST", f"{BASE_URL}/admin/api/deposits/dep_99999999999999/review", admin_headers,
         payload={"status": "approved", "reason": "Test"})

# --- BUG TEST 9: Trader API: Open Additional Account with Malformed Payload ---
run_test("Accounts", "Open Additional Account without Parameters (Crash test)",
         "POST", f"{BASE_URL}/v1/oms/_accounts", follower_headers,
         payload={})

# --- BUG TEST 10: Prop Enrol with Negative or Zero Fee ---
run_test("Prop", "Buy Prop Challenge with Zero / Negative Amount",
         "POST", f"{BASE_URL}/v1/oms/_prop/enrol", follower_headers,
         payload={"program_id": "test_challenge", "fee": -100.0})

with open("scratch/deep_probe_results.json", "w") as f:
    json.dump(results, f, indent=2)

print("\n[+] Deep probes completed. Results written to scratch/deep_probe_results.json")
