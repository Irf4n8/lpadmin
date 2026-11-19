import requests

login_url = "https://lpadmin.blackfx.com/v1/oms/_auth/login"
payload = {
    "email": "mammaster@mailinator.com",
    "password": "Test@1234"
}
r = requests.post(login_url, json=payload)
data = r.json()
token = data["token"]
print("Direct OMS Token:", token)

headers = {"Authorization": f"Bearer {token}"}
pos_url = "https://lpadmin.blackfx.com/v1/oms/real/positions?status=OPEN"
r_pos = requests.get(pos_url, headers=headers)
print("GET /positions status:", r_pos.status_code)
print("Positions response:", r_pos.json())
