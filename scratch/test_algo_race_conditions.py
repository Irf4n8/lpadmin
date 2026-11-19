import requests
import concurrent.futures
import time
import json

BASE_URL = "https://lpadmin.blackfx.com"
PWD = "12345678"

# Login
s = requests.Session()
s.post(f"{BASE_URL}/api/auth/login", json={"email": "mamm@mailinator.com", "password": PWD})
tok = s.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
headers = {"x-token": tok, "Content-Type": "application/json"}

print("=" * 70)
print("ALGO TRADING RACE CONDITION & CONCURRENCY TEST SUITE (AL01 - AL07 / BR14)")
print("=" * 70)

# Step 1: Create an Algo instance
r_create = s.post(f"{BASE_URL}/v1/chart/algo/createAlgo", headers=headers, json={
    "name": "RaceTestAlgo",
    "description": "Concurrency Testing",
    "source": "// Concurrency Algo Code\nfunction onTick() { return 1; }"
})
print("Create Algo:", r_create.status_code, r_create.text)
algo_id = r_create.json().get("uid") or r_create.json().get("id") or r_create.json().get("data", {}).get("uid")
print("Algo UID:", algo_id)

results = {}

# -------------------------------------------------------------
# TEST AL02 / BR14: Simultaneous Save / Overwrite Conflict
# Two tabs / browsers save differing algo source codes at the exact same millisecond
# -------------------------------------------------------------
print("\n" + "-" * 50)
print("TEST AL05 / BR14: Concurrent Save Race (Lost Update / Versioning)")
print("-" * 50)

def save_tab_a():
    return "tab_a", requests.post(f"{BASE_URL}/v1/chart/algo/saveAlgo", headers=headers, json={
        "uid": algo_id,
        "name": "RaceTestAlgo_A",
        "description": "Saved from Tab A",
        "source": "// CODE FROM TAB A - EMA CROSS"
    })

def save_tab_b():
    return "tab_b", requests.post(f"{BASE_URL}/v1/chart/algo/saveAlgo", headers=headers, json={
        "uid": algo_id,
        "name": "RaceTestAlgo_B",
        "description": "Saved from Tab B",
        "source": "// CODE FROM TAB B - RSI BREAKOUT"
    })

with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
    f_a = ex.submit(save_tab_a)
    f_b = ex.submit(save_tab_b)
    res_a = f_a.result()
    res_b = f_b.result()

print(f"Tab A Save Status: {res_a[1].status_code}, Body: {res_a[1].text}")
print(f"Tab B Save Status: {res_b[1].status_code}, Body: {res_b[1].text}")

# Check final saved state
r_get = s.post(f"{BASE_URL}/v1/chart/algo/getAlgo", headers=headers, json={"uid": algo_id})
print(f"Final State in DB: {r_get.status_code}, Body: {r_get.text}")

# -------------------------------------------------------------
# TEST AL07: Stop Algo -> Immediately Restart Race Condition
# -------------------------------------------------------------
print("\n" + "-" * 50)
print("TEST AL07: Stop -> Immediately Restart Race Condition")
print("-" * 50)

# First activate the algo
s.post(f"{BASE_URL}/v1/chart/algo/setAlgoStatus", headers=headers, json={"uid": algo_id, "is_active": True})

def set_status(status_val):
    return status_val, requests.post(f"{BASE_URL}/v1/chart/algo/setAlgoStatus", headers=headers, json={
        "uid": algo_id,
        "is_active": status_val
    })

# Fire STOP (False) and START (True) concurrently
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
    f_stop = ex.submit(set_status, False)
    f_start = ex.submit(set_status, True)
    r_stop = f_stop.result()
    r_start = f_start.result()

print(f"Stop Call (False) Status: {r_stop[1].status_code}, Body: {r_stop[1].text}")
print(f"Start Call (True) Status: {r_start[1].status_code}, Body: {r_start[1].text}")

# Verify status in getAlgo
r_status_check = s.post(f"{BASE_URL}/v1/chart/algo/getAlgo", headers=headers, json={"uid": algo_id})
print(f"Final Algo Status State: {r_status_check.status_code}, Body: {r_status_check.text}")

# -------------------------------------------------------------
# TEST AL01: Rapid Double Creation (Duplicate Algo Instance)
# -------------------------------------------------------------
print("\n" + "-" * 50)
print("TEST AL01: Rapid Double Creation from Double-Click")
print("-" * 50)

def create_algo_click(click_i):
    return click_i, requests.post(f"{BASE_URL}/v1/chart/algo/createAlgo", headers=headers, json={
        "name": "RapidClickAlgo",
        "description": "Double click test",
        "source": "// Single click expected"
    })

with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
    c1 = ex.submit(create_algo_click, 1)
    c2 = ex.submit(create_algo_click, 2)
    rc1 = c1.result()
    rc2 = c2.result()

print(f"Click 1: {rc1[1].status_code}, Body: {rc1[1].text}")
print(f"Click 2: {rc2[1].status_code}, Body: {rc2[1].text}")

# Cleanup
if algo_id:
    s.post(f"{BASE_URL}/v1/chart/algo/deleteAlgo", headers=headers, json={"uid": algo_id})

for rc in [rc1, rc2]:
    try:
        uid = rc[1].json().get("data", {}).get("uid") or rc[1].json().get("uid")
        if uid:
            s.post(f"{BASE_URL}/v1/chart/algo/deleteAlgo", headers=headers, json={"uid": uid})
    except:
        pass

print("\nCleanup complete.")
