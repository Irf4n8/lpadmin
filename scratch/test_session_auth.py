import requests

base_url = "https://lpadmin.blackfx.com"
s = requests.Session()
r = s.post(f"{base_url}/api/auth/login", json={"email": "mamm@mailinator.com", "password": "12345678"}, timeout=10)
print("api/auth/login status:", r.status_code)
print("api/auth/login body:", r.text[:300])

r_tok = s.post(f"{base_url}/api/auth/chart-token", timeout=10)
print("chart-token status:", r_tok.status_code)
print("chart-token body:", r_tok.text[:300])

# Check follower mamf1
s2 = requests.Session()
r2 = s2.post(f"{base_url}/api/auth/login", json={"email": "mamf1@mailinator.com", "password": "12345678"}, timeout=10)
print("mamf1 login status:", r2.status_code)
print("mamf1 login body:", r2.text[:300])
