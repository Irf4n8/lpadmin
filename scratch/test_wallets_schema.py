import requests

f_s = requests.Session()
f_s.post('https://lpadmin.blackfx.com/api/auth/login', json={'email': 'mamf1@mailinator.com', 'password': '12345678'})
f_tok = f_s.post('https://lpadmin.blackfx.com/api/auth/chart-token').json().get('token')
headers = {'Authorization': f'Bearer {f_tok}', 'Content-Type': 'application/json'}

# Check get wallets
r_wallets = f_s.get('https://lpadmin.blackfx.com/v1/oms/real/wallets', headers=headers)
print("Wallets status:", r_wallets.status_code, r_wallets.json())

# Test wallet transfer payload combinations
tests = [
    {"wallet": "client", "amount": -100, "direction": "deposit"},
    {"from": "real", "to": "client", "amount": -100},
    {"wallet": "client", "amount": -100, "from": "real", "to": "client"},
    {"wallet": "client", "action": "deposit", "amount": -100}
]

for t in tests:
    r = f_s.post('https://lpadmin.blackfx.com/v1/oms/real/wallets/transfer', headers=headers, json=t)
    print(f"Payload {t} -> Status {r.status_code}, Body: {r.text}")
