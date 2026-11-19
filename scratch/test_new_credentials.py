import requests

url = "https://lpadmin.blackfx.com/v1/oms/_auth/login"

for email in ["mamm@mailinator.com", "mamf1@mailinator.com", "mamf100@mailinator.com"]:
    r = requests.post(url, json={"email": email, "password": "12345678"})
    print(email, "login status:", r.status_code, "success:", r.json().get("success") if r.status_code == 200 else r.text[:100])
