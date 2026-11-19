import requests
import json

BASE_URL = "https://lpadmin.blackfx.com"
ADMIN_EMAIL = "lpadmin@blacktrader.com"
ADMIN_PASSWORD = "Raj1234!"
MASTER_EMAIL = "mamm@mailinator.com"

# 1. Admin Login
s_adm = requests.Session()
r_adm = s_adm.post(f"{BASE_URL}/admin/api/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
t_adm = r_adm.json().get("token")
h_adm = {"Authorization": f"Bearer {t_adm}", "Content-Type": "application/json"}

# 2. Get all members
m_list = s_adm.get(f"{BASE_URL}/admin/api/members", headers=h_adm).json().get("members", [])
print(f"Total Members in System: {len(m_list)}")

# Filter mamf followers
mamf_members = [m for m in m_list if m.get("email", "").startswith("mamf")]
print(f"Total mamf followers found: {len(mamf_members)}")

# Master info
master = next((m for m in m_list if m.get("email") == MASTER_EMAIL), None)
print(f"\n--- MASTER ({MASTER_EMAIL}) ---")
if master:
    print(f"  Member ID: {master.get('member_id')}")
    print(f"  Status   : {master.get('status')}")
    print(f"  Book     : {master.get('book')}")
    print(f"  Real Bal : ${master.get('balances', {}).get('real', 0):,.2f}")
    print(f"  Paper Bal: ${master.get('balances', {}).get('paper', 0):,.2f}")

# Group followers by balance distribution
bal_summary = {
    "zero_balance": [],
    "sub_10k": [],
    "exactly_10k": [],
    "high_net_worth": [],
    "negative": []
}

books_count = {"a": 0, "b": 0, "other": 0}
status_count = {"active": 0, "disabled": 0, "other": 0}

for m in mamf_members:
    em = m.get("email")
    real_bal = float(m.get("balances", {}).get("real", 0))
    st = m.get("status")
    bk = m.get("book")
    
    books_count[bk] = books_count.get(bk, 0) + 1
    status_count[st] = status_count.get(st, 0) + 1
    
    if real_bal < 0:
        bal_summary["negative"].append((em, real_bal))
    elif real_bal == 0:
        bal_summary["zero_balance"].append(em)
    elif real_bal < 10000:
        bal_summary["sub_10k"].append((em, real_bal))
    elif real_bal <= 100000:
        bal_summary["exactly_10k"].append((em, real_bal))
    else:
        bal_summary["high_net_worth"].append((em, real_bal))

print("\n--- FOLLOWER FLEET BALANCE DISTRIBUTION ---")
print(f"Negative Balance Accounts : {len(bal_summary['negative'])}")
print(f"Zero Balance Accounts     : {len(bal_summary['zero_balance'])}")
print(f"Under $10k Accounts       : {len(bal_summary['sub_10k'])} (Sample: {bal_summary['sub_10k'][:5]})")
print(f"$10k - $100k Accounts     : {len(bal_summary['exactly_10k'])}")
print(f"High Net Worth (>$100k)   : {len(bal_summary['high_net_worth'])} (Sample: {bal_summary['high_net_worth'][:5]})")
print(f"Book Types                : {books_count}")
print(f"Account Statuses          : {status_count}")

# Check MAM Master Follows and High-Water Mark state
s_m = requests.Session()
s_m.post(f"{BASE_URL}/api/auth/login", json={"email": MASTER_EMAIL, "password": "12345678"})
t_m = s_m.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
h_m = {"Authorization": f"Bearer {t_m}", "Content-Type": "application/json"}

r_shares = s_m.get(f"{BASE_URL}/v1/oms/real/mam/shares?role=master", headers=h_m)
shares_data = r_shares.json()
print(f"\n--- MAM PROFIT SHARES AUDIT ---")
print(f"Total Master Profit Shares Earned: ${shares_data.get('master_share_total', 0):,.4f}")
print(f"Total Profit Share Events Logged : {len(shares_data.get('shares', []))}")
if shares_data.get("shares"):
    print("Latest Share Event:", shares_data.get("shares")[-1])
