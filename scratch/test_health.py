import requests

r = requests.get("http://localhost:8500/api/health", timeout=10)
print("Health status:", r.status_code)
print(r.text[:500])
