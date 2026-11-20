"""Restore all fleet accounts to baseline balances."""
import requests

BASE_URL = "https://lpadmin.blackfx.com"
adm_r = requests.post(f"{BASE_URL}/admin/api/login", json={"email": "lpadmin@blacktrader.com", "password": "Raj1234!"})
adm_token = adm_r.json().get("token")
adm_headers = {"Authorization": f"Bearer {adm_token}", "Content-Type": "application/json"}

accounts = [
    ("mem_11434b0b9d9d210899", 100000, "mamm"),
    ("mem_0ea679062ffd38adf7", 10000, "mamf1"),
    ("mem_87cc39bb4ddf52a026", 10000, "mamf2"),
    ("mem_761e39f83d27137624", 10000, "mamf3"),
]
for mid, bal, name in accounts:
    r = requests.post(f"{BASE_URL}/admin/api/members/{mid}/balance",
        headers=adm_headers, json={"instance": "real", "balance": bal, "force": True})
    print(f"{name}: set to ${bal} -> {r.status_code}")
print("Fleet restored.")
