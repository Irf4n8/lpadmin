import requests

login_url = "https://lpadmin.blackfx.com/v1/oms/_auth/login"
r = requests.post(login_url, json={"email": "mamm@mailinator.com", "password": "12345678"})
print("mamm login:", r.status_code)
if r.status_code == 200:
    data = r.json()
    token = data["token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Check if is_master
    rf = requests.get("https://lpadmin.blackfx.com/v1/oms/real/mam/follows", headers=headers)
    print("MAM follows response:", rf.status_code, rf.json() if rf.status_code == 200 else rf.text)
