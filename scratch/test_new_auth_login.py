import requests

url = "https://lpadmin.blackfx.com/oms/_auth/login"
payload = {
    "email": "mammaster@mailinator.com",
    "password": "Test@1234"
}
r = requests.post(url, json=payload)
print("Status code:", r.status_code)
print("Response text:", r.text)
