import requests
import time
import json

base = "http://localhost:8500"

print("=" * 60)
print("1. Verifying GET / and HTML integrity")
r_index = requests.get(f"{base}/", timeout=10)
print(f"GET / Status: {r_index.status_code}")
assert r_index.status_code == 200
assert "mamf1" in r_index.text
assert "mamfollower" not in r_index.text
print("✅ Index HTML contains mamf fleet and zero mamfollower remnants.")

print("=" * 60)
print("2. Verifying GET /api/data cache and fleet structure")
r_data = requests.get(f"{base}/api/data", timeout=10)
print(f"GET /api/data Status: {r_data.status_code}")
assert r_data.status_code == 200
data = r_data.json()
print("Meta:", data.get("meta"))
print("Master Email:", data.get("master", {}).get("email"))
print("Master Client ID:", data.get("master", {}).get("member_id"))
print("Total Followers in Cache:", len(data.get("followers", [])))
if data.get("followers"):
    print("Follower 1:", data["followers"][0].get("email"), "Following:", data["followers"][0].get("following"))
    print("Follower 100:", data["followers"][-1].get("email"), "Following:", data["followers"][-1].get("following"))

print("=" * 60)
print("3. Testing Button: Save Master Profit Share to MAM (/api/manage/master-share)")
r_share = requests.post(f"{base}/api/manage/master-share", json={
    "master_id": "mam",
    "share_percent": 50.0,
    "display_name": "mamm"
}, timeout=15)
print("Share Response:", r_share.status_code, r_share.json())
assert r_share.status_code == 200 and r_share.json().get("success")
print("✅ Master profit share button works!")

print("=" * 60)
print("4. Testing Button: Apply Category Configuration (/api/manage/category)")
r_cat = requests.post(f"{base}/api/manage/category", json={
    "target_type": "range",
    "start": 1,
    "end": 2,
    "category": "multiplier",
    "multiplier": 1.5,
    "share_percent": 50.0
}, timeout=25)
print("Category Response:", r_cat.status_code, r_cat.json())
assert r_cat.status_code == 200 and r_cat.json().get("success")
print("✅ Category configuration button works!")

print("=" * 60)
print("5. Testing Button: Bulk Follow Master (/api/manage/follow)")
r_fol = requests.post(f"{base}/api/manage/follow", json={
    "target_type": "range",
    "start": 1,
    "end": 2,
    "category": "equity",
    "multiplier": 1.0
}, timeout=25)
print("Follow Response:", r_fol.status_code, r_fol.json())
assert r_fol.status_code == 200 and r_fol.json().get("success")
print("✅ Bulk follow button works!")

print("=" * 60)
print("6. Testing Button: Set Account Balances (/api/manage/balance)")
r_bal = requests.post(f"{base}/api/manage/balance", json={
    "target_type": "range",
    "start": 1,
    "end": 2,
    "balance": 10000000.0,
    "instance": "real"
}, timeout=25)
print("Balance Response:", r_bal.status_code, r_bal.json())
assert r_bal.status_code == 200 and r_bal.json().get("success")
print("✅ Account balances button works!")

print("=" * 60)
print("7. Testing Button: Convert Fleet Book (/api/manage/book)")
r_book = requests.post(f"{base}/api/manage/book", json={
    "target_type": "range",
    "start": 1,
    "end": 2,
    "book": "b"
}, timeout=25)
print("Book Response:", r_book.status_code, r_book.json())
assert r_book.status_code == 200 and r_book.json().get("success")
print("✅ Fleet book button works!")

print("=" * 60)
print("8. Testing Button: Broker Setting Toggle (/api/manage/broker-setting)")
r_brk = requests.post(f"{base}/api/manage/broker-setting", json={
    "target_type": "single",
    "single_email": "mamf1@mailinator.com",
    "target_broker": "real",
    "action": "enable",
    "category": "multiplier",
    "multiplier": 1.0
}, timeout=25)
print("Broker Setting Response:", r_brk.status_code, r_brk.json())
assert r_brk.status_code == 200 and r_brk.json().get("success")
print("✅ Broker setting toggle button works!")

print("=" * 60)
print("9. Testing Button: Switch Environment (/api/manage/environment)")
r_env = requests.post(f"{base}/api/manage/environment", json={
    "instance": "real"
}, timeout=10)
print("Environment Response:", r_env.status_code, r_env.json())
assert r_env.status_code == 200 and r_env.json().get("success")
print("✅ Environment switch button works!")

print("=" * 60)
print("ALL DASHBOARD BUTTON ENDPOINTS VERIFIED & WORKING PERFECTLY!")
