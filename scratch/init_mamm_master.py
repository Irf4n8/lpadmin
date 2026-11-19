import requests

login_url = "https://lpadmin.blackfx.com/v1/oms/_auth/login"
r = requests.post(login_url, json={"email": "mamm@mailinator.com", "password": "12345678"})
token = r.json()["token"]
headers = {"Authorization": f"Bearer {token}"}

# Become master on real and paper
for inst in ["real", "paper"]:
    rm = requests.post(f"https://lpadmin.blackfx.com/v1/oms/{inst}/mam/master", headers=headers, json={"display_name": "mamm", "share_percent": 50, "status": "active"})
    print(f"Become master on {inst}:", rm.status_code, rm.json() if rm.status_code == 200 else rm.text)

# Check follows
rf = requests.get("https://lpadmin.blackfx.com/v1/oms/real/mam/follows", headers=headers)
print("Updated follows state:", rf.json())
