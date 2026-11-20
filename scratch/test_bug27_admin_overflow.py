"""
BUG-27: Admin Integer Overflow — Set balance to astronomically large value
Attack: Use Admin API to set a member balance to MAX_INT64 or close to it.
        Check if margin calculations overflow, negative margin level, etc.
"""
import requests, json

BASE_URL = "https://lpadmin.blackfx.com"

# Admin auth
r = requests.post(f"{BASE_URL}/admin/api/login", json={"email": "lpadmin@blacktrader.com", "password": "Raj1234!"})
adm_token = r.json().get("token")
adm_headers = {"Authorization": f"Bearer {adm_token}", "Content-Type": "application/json"}
print("Admin login:", r.status_code)

# Master auth (to check resulting state)
s_m = requests.Session()
s_m.post(f"{BASE_URL}/api/auth/login", json={"email": "mamm@mailinator.com", "password": "12345678"})
t_m = s_m.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
h_m = {"Authorization": f"Bearer {t_m}", "Content-Type": "application/json"}

MASTER_MID = "mem_11434b0b9d9d210899"

test_values = [
    999999999999,       # Very large
    9007199254740992,   # 2^53 (JS MAX_SAFE_INT)
    2147483647,         # INT32_MAX
    9223372036854775807, # INT64_MAX
    -1,                 # Negative (direct admin set)
    -999999,            # Large negative
]

print("\n=== BUG-27: Admin Balance Overflow Tests ===\n")
bugs_found = []

for val in test_values:
    r2 = requests.post(
        f"{BASE_URL}/admin/api/members/{MASTER_MID}/balance",
        headers=adm_headers,
        json={"instance": "real", "balance": val, "force": True}
    )
    print(f"Set balance={val}: {r2.status_code} {r2.text[:150]}")
    
    if r2.status_code == 200:
        # Check actual balance shown
        pos = s_m.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_m).json()
        actual = pos.get("funds", {}).get("balance")
        margin_level = pos.get("funds", {}).get("margin_level")
        equity = pos.get("funds", {}).get("equity")
        print(f"  → Actual balance: {actual}, equity: {equity}, margin_level: {margin_level}")
        
        if actual != val:
            print(f"  🚨 DISCREPANCY: Set {val} but got {actual} (possible overflow/truncation)")
            bugs_found.append({"set_value": val, "actual": actual, "equity": equity})

print(f"\n=== FINDINGS ===")
if bugs_found:
    for b in bugs_found:
        print(f"🚨 BUG-27: set={b['set_value']}, actual={b['actual']} — OVERFLOW/TRUNCATION!")
else:
    print("No overflow detected in admin balance setting.")

# Restore master to $100,000
restore = requests.post(
    f"{BASE_URL}/admin/api/members/{MASTER_MID}/balance",
    headers=adm_headers,
    json={"instance": "real", "balance": 100000, "force": True}
)
print(f"\nRestored master balance: {restore.status_code}")
pos_final = s_m.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_m).json()
print(f"Final balance: {pos_final.get('funds', {}).get('balance')}")
print("\nBUG-27 test complete.")
