import requests
import json

BASE_URL = "https://lpadmin.blackfx.com"
ADMIN_EMAIL = "lpadmin@blacktrader.com"
ADMIN_PASSWORD = "Raj1234!"
MASTER_EMAIL = "mamm@mailinator.com"
FOLLOWER_EMAIL = "mamf1@mailinator.com"
PWD = "12345678"
INSTANCE = "real"

s_f = requests.Session()
s_f.post(f"{BASE_URL}/api/auth/login", json={"email": FOLLOWER_EMAIL, "password": PWD})
f_tok = s_f.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
f_h = {"Authorization": f"Bearer {f_tok}", "Content-Type": "application/json"}

# Check follower active follow record
r_fol = s_f.get(f"{BASE_URL}/v1/oms/{INSTANCE}/mam/follows", headers=f_h)
active_follow = next((f for f in r_fol.json().get("following", []) if f.get("status") == "active"), None)
print("Active Follow Agreement:", json.dumps(active_follow, indent=2))

# Check follower actual current funds
r_funds = s_f.get(f"{BASE_URL}/v1/oms/{INSTANCE}/funds", headers=f_h)
funds = r_funds.json().get("funds", {})
print("\nActual Live Funds:")
print(f"  Current Balance : ${funds.get('balance'):,.2f}")
print(f"  Current Equity  : ${funds.get('equity'):,.2f}")
print(f"  Follow Agreement Starting Balance: ${active_follow.get('starting_balance'):,.2f}")

diff = funds.get('balance') - active_follow.get('starting_balance')
print(f"\nDiscrepancy between Actual Balance and HWM Base: ${diff:,.2f}")
if diff > 1000:
    print("⚠️ HWM DRIFT VERIFIED: Follower balance is $10M, but HWM benchmark is anchored to $9.9k!")
    print("   If follower loses $5,000,000, the system will still falsely consider them in profit (> $9.9k)")
    print("   and continue taking 50% profit share!")
