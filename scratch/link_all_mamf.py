import requests, concurrent.futures, time

master_cid = "mem_11434b0b9d9d210899" # mamm@mailinator.com
base_url = "https://lpadmin.blackfx.com/v1"

def link_follower(idx):
    email = f"mamf{idx}@mailinator.com"
    pwd = "12345678"
    try:
        r_log = requests.post(f"{base_url}/oms/_auth/login", json={"email": email, "password": pwd}, timeout=10)
        if r_log.status_code != 200:
            return idx, False, f"Login failed: {r_log.status_code}"
        tok = r_log.json().get("token")
        headers = {"Authorization": f"Bearer {tok}"}
        
        # Follow mamm on real
        payload = {"master_client_id": master_cid, "multiplier": 1.0}
        rf = requests.post(f"{base_url}/oms/real/mam/follow", headers=headers, json=payload, timeout=10)
        return idx, rf.status_code == 200, rf.json() if rf.status_code == 200 else rf.text
    except Exception as e:
        return idx, False, str(e)

print("Linking mamf1..100 to mamm on real...")
t0 = time.time()
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
    results = list(ex.map(link_follower, range(1, 101)))

dur = time.time() - t0
success_cnt = sum(1 for r in results if r[1])
print(f"Finished linking in {dur:.1f}s. Success: {success_cnt}/100")
