"""
BUG-36: Unthrottled Admin Balance Override (Brute Force Financial Attack)
Attack: Rapid-fire 50 consecutive admin balance SET calls to test:
  1. No rate limiting on admin/api/members/{id}/balance
  2. Race condition in rapid successive sets (is each delta atomically computed?)
  3. Can attacker use this to slowly drain all user accounts?

BUG-37: Orphaned Follower After Master Account Deletion/Deactivation
         Check if follower subscriptions survive master deactivation.
"""
import requests, json, time, concurrent.futures

BASE_URL = "https://lpadmin.blackfx.com"

adm_r = requests.post(f"{BASE_URL}/admin/api/login", json={"email": "lpadmin@blacktrader.com", "password": "Raj1234!"})
adm_token = adm_r.json().get("token")
adm_headers = {"Authorization": f"Bearer {adm_token}", "Content-Type": "application/json"}

MASTER_ID = "mem_11434b0b9d9d210899"

print("=== BUG-36: Unthrottled Admin Balance Override ===\n")

# Fire 20 rapid balance changes and see if any are dropped or cause race
results = []
start = time.time()

def set_balance(val):
    r = requests.post(
        f"{BASE_URL}/admin/api/members/{MASTER_ID}/balance",
        headers=adm_headers,
        json={"instance": "real", "balance": val, "force": True}
    )
    return {"val": val, "status": r.status_code, "delta": r.json().get("delta") if r.status_code == 200 else None}

# Alternating high/low values in parallel
test_values = [100000 + i * 1000 for i in range(20)]
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
    futures = [ex.submit(set_balance, v) for v in test_values]
    results = [f.result() for f in concurrent.futures.as_completed(futures)]

elapsed = time.time() - start
print(f"Completed 20 balance sets in {elapsed:.2f}s")
print(f"All 200 OK: {all(r['status'] == 200 for r in results)}")
failed = [r for r in results if r['status'] != 200]
if failed:
    print(f"Failed: {failed}")
else:
    print("🚨 BUG-36: No rate limiting! 20 concurrent admin balance overrides all succeeded!")
    print(f"   Rate: {20/elapsed:.1f} requests/sec with no throttling")

# Check final balance
s_m = requests.Session()
s_m.post(f"{BASE_URL}/api/auth/login", json={"email": "mamm@mailinator.com", "password": "12345678"})
t_m = s_m.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
h_m = {"Authorization": f"Bearer {t_m}", "Content-Type": "application/json"}
final_bal = s_m.get(f"{BASE_URL}/v1/oms/real/positions", headers=h_m).json().get("funds", {}).get("balance")
print(f"Final balance after race: {final_bal} (expected one of: {test_values})")
if final_bal not in test_values:
    print(f"🚨 BUG-36b: RACE CONDITION! Final balance {final_bal} is not one of the 20 set values!")

# Restore
requests.post(f"{BASE_URL}/admin/api/members/{MASTER_ID}/balance",
    headers=adm_headers, json={"instance": "real", "balance": 100000, "force": True})
print("Restored master balance.")

print("\n=== BUG-37: MAM subscription state check ===")
# Check active subscriptions list via master's view
s_m2 = requests.Session()
s_m2.post(f"{BASE_URL}/api/auth/login", json={"email": "mamm@mailinator.com", "password": "12345678"})
t_m2 = s_m2.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
h_m2 = {"Authorization": f"Bearer {t_m2}", "Content-Type": "application/json"}

follows_resp = s_m2.get(f"{BASE_URL}/v1/oms/real/mam/follows", headers=h_m2)
follows_data = follows_resp.json()
print(f"Master followers list: {follows_resp.status_code}")
followers = follows_data.get("followers", [])
print(f"Total followers: {len(followers)}")

# Check for followers NOT in our test set (data leak!)
our_ids = {"mem_0ea679062ffd38adf7", "mem_87cc39bb4ddf52a026", "mem_761e39f83d27137624"}
for f in followers:
    fid = f.get("follower_client_id")
    fname = f.get("follower_name")
    sb = f.get("starting_balance")
    print(f"  Follower: id={fid}, name={fname}, starting_bal={sb}")
    if fid and fid not in our_ids:
        print(f"  🚨 BUG-37/33: Unknown follower {fname} ({fid}) visible in master's follower list!")
        print(f"     This may be a real user account — data leak of PII (name, balance)!")

print("\nBUG-36/37 test complete.")
