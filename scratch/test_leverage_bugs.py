import requests
import json

BASE_URL = "https://lpadmin.blackfx.com"
TEST_EMAIL = "mamf90@mailinator.com"
PWD = "12345678"

s = requests.Session()
s.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": PWD})
tok = s.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}

print("=" * 70)
print("AUDITING BROKER LEVERAGE CONFIGURATION & MID-TRADE MODIFICATIONS")
print("=" * 70)

# Check current leverage
r_get = s.post(f"{BASE_URL}/v1/oms/_brokers/binance/leverage", headers=h, json={})
print("Current Leverage Config Status:", r_get.status_code, r_get.text)

# Test 1: Negative Leverage (-10x)
print("\n--- TEST 1: Negative Leverage (-10) ---")
r_neg = s.post(f"{BASE_URL}/v1/oms/_brokers/binance/leverage", headers=h, json={
    "symbol": "BINANCE:BTCUSDT",
    "leverage": -10
})
print("Negative Leverage Status:", r_neg.status_code, r_neg.text)

# Test 2: Zero Leverage (0x)
print("\n--- TEST 2: Zero Leverage (0) ---")
r_zero = s.post(f"{BASE_URL}/v1/oms/_brokers/binance/leverage", headers=h, json={
    "symbol": "BINANCE:BTCUSDT",
    "leverage": 0
})
print("Zero Leverage Status:", r_zero.status_code, r_zero.text)

# Test 3: Extreme Astronomical Leverage (1,000,000x)
print("\n--- TEST 3: Extreme Leverage (1,000,000) ---")
r_ext = s.post(f"{BASE_URL}/v1/oms/_brokers/binance/leverage", headers=h, json={
    "symbol": "BINANCE:BTCUSDT",
    "leverage": 1000000
})
print("Extreme Leverage Status:", r_ext.status_code, r_ext.text)

# Test 4: Modify Leverage While In An Active Trade
print("\n--- TEST 4: Leverage Modification While In Position ---")
# Open a position
r_open = s.post(f"{BASE_URL}/v1/oms/real/orders", headers=h, json={
    "symbol": "BINANCE:BTCUSDT", "side": "BUY", "type": "MARKET", "qty": 0.01
})
pos_oid = r_open.json().get("order", {}).get("market_order_id")
print("Position Opened:", pos_oid)

r_funds_b4 = s.get(f"{BASE_URL}/v1/oms/real/funds", headers=h)
used_margin_b4 = r_funds_b4.json().get("funds", {}).get("used_margin")
print("Used Margin Before Leverage Change:", used_margin_b4)

# Change leverage from default (100x) to 10x (Requires 10x more margin!)
r_change = s.post(f"{BASE_URL}/v1/oms/_brokers/binance/leverage", headers=h, json={
    "symbol": "BINANCE:BTCUSDT",
    "leverage": 10
})
print("Change Leverage to 10x Status:", r_change.status_code, r_change.text)

r_funds_after = s.get(f"{BASE_URL}/v1/oms/real/funds", headers=h)
used_margin_after = r_funds_after.json().get("funds", {}).get("used_margin")
print("Used Margin After Leverage Change:", used_margin_after)

# Cleanup
if pos_oid:
    s.post(f"{BASE_URL}/v1/oms/real/positions/{pos_oid}/squareoff", headers=h)
s.post(f"{BASE_URL}/v1/oms/_brokers/binance/leverage", headers=h, json={
    "symbol": "BINANCE:BTCUSDT", "leverage": 100
})
print("\nCleanup completed.")
