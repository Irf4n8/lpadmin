"""
BUG-38: Profit Share Percentage Manipulation — Can follower set share_percent to 0 or negative?
Attack: When re-subscribing, pass extreme values for share_percent to bypass MAM fee.

BUG-39: MAM Subscription with Duplicate/Conflicting Parameters  
Attack: Submit follow request with contradictory fields simultaneously
        (e.g., method="lot_multiplier" but also include "equity_percent" fields)

BUG-40: Account-to-Account Follow (Circular MAM) — Can follower follow another follower?
         If follower follows follower creates circular dependency → infinite replication loop?
"""
import requests, json

BASE_URL = "https://lpadmin.blackfx.com"

def make_session(email, password):
    s = requests.Session()
    s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
    t = s.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
    return s, {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}

s_m, h_m = make_session("mamm@mailinator.com", "12345678")
s_f1, h_f1 = make_session("mamf1@mailinator.com", "12345678")
s_f2, h_f2 = make_session("mamf2@mailinator.com", "12345678")
s_f3, h_f3 = make_session("mamf3@mailinator.com", "12345678")

MASTER_ID = "mem_11434b0b9d9d210899"
F1_ID = "mem_0ea679062ffd38adf7"
F2_ID = "mem_87cc39bb4ddf52a026"
F3_ID = "mem_761e39f83d27137624"

print("=== BUG-38: Share Percent Manipulation ===\n")
# Try subscribe with 0% share
for share_val in [0, -1, -100, 101, 999, 0.001, None]:
    payload = {"master_id": MASTER_ID, "multiplier": 1.0}
    if share_val is not None:
        payload["share_percent"] = share_val
    r = s_f1.post(f"{BASE_URL}/v1/oms/real/mam/follow", headers=h_f1, json=payload)
    print(f"share_percent={share_val}: {r.status_code} {r.text[:150]}")
    if r.status_code == 200:
        result = r.json()
        actual_share = result.get("share_percent") or result.get("follow", {}).get("share_percent")
        print(f"  → Actual share_percent accepted: {actual_share}")
        if share_val is not None and share_val <= 0:
            print(f"  🚨 BUG-38: Negative/zero share_percent={share_val} accepted!")

print("\n=== BUG-39: Contradictory MAM Follow Parameters ===\n")
contradictory_payloads = [
    {"master_id": MASTER_ID, "multiplier": 1.0, "equity_percent": 50, "method": "both"},
    {"master_id": MASTER_ID, "multiplier": -1.0},
    {"master_id": MASTER_ID, "multiplier": 0},
    {"master_id": MASTER_ID, "multiplier": 999999},
    {"master_id": MASTER_ID},  # No multiplier at all
    {"master_id": MASTER_ID, "method": "equity_percent", "equity_percent": 150},  # > 100%
    {"master_id": MASTER_ID, "method": "equity_percent", "equity_percent": -50},  # Negative
    {"master_id": MASTER_ID, "multiplier": 1.0, "share_percent": 50, "extra_field": "injection_test"},
]
for i, payload in enumerate(contradictory_payloads):
    r = s_f1.post(f"{BASE_URL}/v1/oms/real/mam/follow", headers=h_f1, json=payload)
    print(f"[{i+1}] {json.dumps(payload)}: {r.status_code} {r.text[:200]}")
    if r.status_code == 200:
        rdata = r.json()
        print(f"  🚨 Accepted! Response: {json.dumps(rdata)[:200]}")

print("\n=== BUG-40: Circular MAM — Follower following Follower ===\n")
# Can F2 follow F1 (while F1 follows master)?
r_circ = s_f2.post(f"{BASE_URL}/v1/oms/real/mam/follow", headers=h_f2, json={
    "master_id": F1_ID, "multiplier": 1.0
})
print(f"F2 following F1 (follower): {r_circ.status_code} {r_circ.text[:300]}")
if r_circ.status_code == 200:
    print("🚨 BUG-40 CONFIRMED: Follower can follow another follower — potential circular replication loop!")
    # Undo it
    s_f2.post(f"{BASE_URL}/v1/oms/real/mam/unfollow", headers=h_f2, json={"master_id": F1_ID})
    print("Unfollowed F1.")

# Can master follow itself?
r_self = s_m.post(f"{BASE_URL}/v1/oms/real/mam/follow", headers=h_m, json={
    "master_id": MASTER_ID, "multiplier": 1.0
})
print(f"Master following itself: {r_self.status_code} {r_self.text[:200]}")
if r_self.status_code == 200:
    print("🚨 BUG-40b: Master can follow itself — self-referential loop!")

# Can F3 follow F2?
r_f3f2 = s_f3.post(f"{BASE_URL}/v1/oms/real/mam/follow", headers=h_f3, json={
    "master_id": F2_ID, "multiplier": 1.0
})
print(f"F3 following F2: {r_f3f2.status_code} {r_f3f2.text[:200]}")
if r_f3f2.status_code == 200:
    print("🚨 BUG-40c: Cross-follower subscription allowed!")
    s_f3.post(f"{BASE_URL}/v1/oms/real/mam/unfollow", headers=h_f3, json={"master_id": F2_ID})

print("\nBUG-38/39/40 test complete.")
