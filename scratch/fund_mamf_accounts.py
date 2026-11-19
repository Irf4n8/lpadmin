import requests, concurrent.futures

r_admin_login = requests.post("https://lpadmin.blackfx.com/admin/api/login", json={"email": "lpadmin@blacktrader.com", "password": "Raj1234!", "remember": True})
admin_token = r_admin_login.json().get("token")
headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

r_mem = requests.get("https://lpadmin.blackfx.com/admin/api/members", headers={"Authorization": f"Bearer {admin_token}"})
members = r_mem.json().get("members", [])

mamf_members = [m for m in members if m.get("email", "").startswith("mamf") and "@" in m.get("email", "")]
print(f"Found {len(mamf_members)} mamf members.")

# Check balances
zero_cnt = sum(1 for m in mamf_members if m.get("balances", {}).get("real", 0) <= 0)
print(f"mamf accounts with 0 or negative real balance: {zero_cnt}/{len(mamf_members)}")

def fund_member(m):
    mid = m["member_id"]
    email = m["email"]
    payload = {"instance": "real", "balance": 10000000, "remark": "Initial Funding for Testing", "force": True}
    rf = requests.post(f"https://lpadmin.blackfx.com/admin/api/members/{mid}/balance", headers=headers, json=payload, timeout=10)
    return email, rf.status_code == 200

if zero_cnt > 0:
    print("Funding mamf accounts with $10,000,000 balance on real...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        res = list(ex.map(fund_member, mamf_members))
    print(f"Funded {sum(1 for r in res if r[1])}/{len(res)} accounts successfully.")
