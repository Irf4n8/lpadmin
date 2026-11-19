import requests

login_url = "https://lpadmin.blackfx.com/v1/oms/_auth/login"
r = requests.post(login_url, json={"email": "mamm@mailinator.com", "password": "12345678"})
token = r.json()["token"]
headers = {"Authorization": f"Bearer {token}"}

rf = requests.get("https://lpadmin.blackfx.com/v1/oms/real/mam/follows", headers=headers)
data = rf.json()
followers = data.get("followers", [])
print(f"Master {data.get('master', {}).get('display_name')} ({data.get('master', {}).get('client_id')}) has {len(followers)} active followers on real!")
print("First 3 followers:", [f.get("follower_name") for f in followers[:3]])
print("Last 3 followers:", [f.get("follower_name") for f in followers[-3:]])
