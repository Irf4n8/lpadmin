import requests

url = "https://lpadmin.blackfx.com/v1/oms/_auth/login"
payload = {
    "email": "mammaster@mailinator.com",
    "password": "Test@1234"
}
r = requests.post(url, json=payload)
print("Status code:", r.status_code)
print("Response JSON:", r.json() if r.status_code == 200 else r.text)
