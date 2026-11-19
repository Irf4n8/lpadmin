import requests

base = "http://localhost:8500"

print("--- Testing GET / ---")
try:
    r = requests.get(f"{base}/", timeout=5)
    print("Status:", r.status_code, "Length:", len(r.text))
except Exception as e:
    print("Error:", e)

print("\n--- Testing GET /api/data ---")
try:
    r = requests.get(f"{base}/api/data", timeout=5)
    print("Status:", r.status_code)
    data = r.json()
    print("Meta:", data.get("meta"))
    print("Master email:", data.get("master", {}).get("email"))
    print("Master client_id:", data.get("master", {}).get("client_id"))
    print("Followers count in cache:", len(data.get("followers", [])))
    if data.get("followers"):
        print("First follower:", data.get("followers")[0])
except Exception as e:
    print("Error:", e)

print("\n--- Testing GET /api/suites ---")
try:
    r = requests.get(f"{base}/api/suites", timeout=5)
    print("Status:", r.status_code, "Suites:", len(r.json().get("suites", [])))
except Exception as e:
    print("Error:", e)
