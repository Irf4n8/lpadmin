import requests

BASE_URL = "https://lpadmin.blackfx.com"
r = requests.post(f"{BASE_URL}/admin/api/login", json={"email": "lpadmin@blacktrader.com", "password": "Raj1234!"})
adm_token = r.json().get("token")
adm_headers = {"Authorization": f"Bearer {adm_token}", "Content-Type": "application/json"}

# Try setting balance to 0.0
r_bal = requests.post(f"{BASE_URL}/admin/api/members/mem_0ea679062ffd38adf7/balance", 
                      json={"instance": "real", "balance": 0.0}, 
                      headers=adm_headers)
print("Setting balance to 0.0 response:", r_bal.status_code, r_bal.text)

# Try setting balance to 5.0
r_bal5 = requests.post(f"{BASE_URL}/admin/api/members/mem_0ea679062ffd38adf7/balance", 
                      json={"instance": "real", "balance": 5.0}, 
                      headers=adm_headers)
print("Setting balance to 5.0 response:", r_bal5.status_code, r_bal5.text)

# Try setting balance to negative -50.0
r_bal_neg = requests.post(f"{BASE_URL}/admin/api/members/mem_0ea679062ffd38adf7/balance", 
                          json={"instance": "real", "balance": -50.0}, 
                          headers=adm_headers)
print("Setting balance to -50.0 response:", r_bal_neg.status_code, r_bal_neg.text)
