import requests

r_login = requests.post("https://lpadmin.blackfx.com/v1/oms/_auth/login", json={
    "email": "mamf1@mailinator.com",
    "password": "12345678"
})
print("OMS _auth/login status:", r_login.status_code)
token = r_login.json().get("token")
print("OMS session token:", token[:20] if token else "None")

headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# Test 1: Bulk squareoff with string instead of list (Crash test)
r_bulk_crash = requests.post("https://lpadmin.blackfx.com/v1/oms/real/positions/bulk/squareoff", headers=headers, json={
    "market_order_ids": "not_an_array"
})
print("Bulk squareoff with string instead of array:", r_bulk_crash.status_code, r_bulk_crash.text)

# Test 2: Bulk squareoff with empty array
r_bulk_empty = requests.post("https://lpadmin.blackfx.com/v1/oms/real/positions/bulk/squareoff", headers=headers, json={
    "market_order_ids": []
})
print("Bulk squareoff with empty array:", r_bulk_empty.status_code, r_bulk_empty.text)

# Test 3: Position reduce with qty = 0
r_reduce_zero = requests.post("https://lpadmin.blackfx.com/v1/oms/real/positions/some_id/reduce", headers=headers, json={
    "qty": 0.0
})
print("Position reduce with qty = 0:", r_reduce_zero.status_code, r_reduce_zero.text)

# Test 4: Position reduce with malformed order ID
r_reduce_malformed = requests.post("https://lpadmin.blackfx.com/v1/oms/real/positions/../../reduce", headers=headers, json={
    "qty": 1.0
})
print("Position reduce with path traversal order ID:", r_reduce_malformed.status_code, r_reduce_malformed.text)
