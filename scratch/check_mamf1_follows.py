import requests

url = "https://lpadmin.blackfx.com/v1/oms/_auth/login"
r = requests.post(url, json={"email": "mamf1@mailinator.com", "password": "12345678"})
token = r.json()["token"]
headers = {"Authorization": f"Bearer {token}"}

rf = requests.get("https://lpadmin.blackfx.com/v1/oms/real/mam/follows", headers=headers)
print("mamf1 follows on real:", rf.json())
