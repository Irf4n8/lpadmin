import requests
import json
import time
import concurrent.futures

BASE_URL = "https://lpadmin.blackfx.com"
ADMIN_EMAIL = "lpadmin@blacktrader.com"
ADMIN_PASSWORD = "Raj1234!"
MASTER_EMAIL = "mamm@mailinator.com"
PWD = "12345678"
INSTANCE = "real"
SYMBOL = "BINANCE:BTCUSDT"

print("=" * 70)
print("🏁 COMPREHENSIVE RACE CONDITION & BALANCE INTEGRITY AUDIT")
print("=" * 70)

# 1. Admin Login
adm_s = requests.Session()
r_adm = adm_s.post(f"{BASE_URL}/admin/api/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
adm_tok = r_adm.json().get("token")
adm_headers = {"Authorization": f"Bearer {adm_tok}", "Content-Type": "application/json"}

# 2. Master Login
m_s = requests.Session()
m_s.post(f"{BASE_URL}/api/auth/login", json={"email": MASTER_EMAIL, "password": PWD})
m_tok = m_s.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
m_headers = {"Authorization": f"Bearer {m_tok}", "Content-Type": "application/json"}

# 3. Follower Fleet Sessions (Sample: mamf1, mamf2, mamf3, mamf4, mamf5)
follower_sessions = {}
for i in [1, 2, 3, 4, 5]:
    f_email = f"mamf{i}@mailinator.com"
    s = requests.Session()
    s.post(f"{BASE_URL}/api/auth/login", json={"email": f_email, "password": PWD})
    tok = s.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
    follower_sessions[f_email] = {
        "session": s,
        "token": tok,
        "headers": {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    }

print(f"[+] Initialized sessions for Master and 5 Followers.")

# Ensure followers are linked to Master in Multiplier 1.0x mode
for em, f_data in follower_sessions.items():
    f_data["session"].post(f"{BASE_URL}/v1/oms/{INSTANCE}/mam/follow", headers=f_data["headers"], json={
        "master_client_id": "mem_11434b0b9d9d210899", "method": "multiplier", "multiplier": 1.0, "share_percent": 50.0
    })

# --------------------------------------------------------------------------
# EXPERIMENT 1: Rapid Open-Close Race Condition (Position Ghosting)
# --------------------------------------------------------------------------
print("\n" + "=" * 50)
print("TEST 1: Rapid Fire Open & Instant Square-Off Race Condition")
print("=" * 50)

# Master places order and IMMEDIATELY squares it off in zero delay
r_open = m_s.post(f"{BASE_URL}/v1/oms/{INSTANCE}/orders", headers=m_headers, json={
    "symbol": SYMBOL, "side": "BUY", "type": "MARKET", "qty": 0.02
})
ord_data = r_open.json().get("order", {})
mkt_ord_id = ord_data.get("market_order_id")
print(f"Master Order Placed: {mkt_ord_id}")

# ZERO DELAY: Instant Square-Off call immediately after order return!
r_close_instant = m_s.post(f"{BASE_URL}/v1/oms/{INSTANCE}/positions/{mkt_ord_id}/squareoff", headers=m_headers)
print(f"Master Instant Square-Off Status: {r_close_instant.status_code}, Response: {r_close_instant.text[:200]}")

# Wait 3 seconds for all follower replication queues to settle
time.sleep(3)

# Check Master position
r_m_pos = m_s.get(f"{BASE_URL}/v1/oms/{INSTANCE}/positions", headers=m_headers)
m_remaining = len(r_m_pos.json().get("positions", []))
print(f"Master Open Positions Remaining: {m_remaining}")

# Check all 5 followers for orphaned ghost positions!
orphaned_positions = {}
for em, f_data in follower_sessions.items():
    r_pos = f_data["session"].get(f"{BASE_URL}/v1/oms/{INSTANCE}/positions", headers=f_data["headers"])
    open_pos = r_pos.json().get("positions", [])
    if len(open_pos) > 0:
        orphaned_positions[em] = open_pos
        print(f"⚠️ RACE CONDITION DETECTED! {em} has {len(open_pos)} orphaned position(s)!")
        for p in open_pos:
            print(f"   Orphaned Position ID: {p.get('position_id')}, Qty: {p.get('net_qty')}, Symbol: {p.get('symbol')}")
    else:
        print(f"✅ {em}: Clean (0 open positions)")

# Clean up any orphaned positions
for em, pos_list in orphaned_positions.items():
    for p in pos_list:
        follower_sessions[em]["session"].post(
            f"{BASE_URL}/v1/oms/{INSTANCE}/positions/{p.get('market_order_id')}/squareoff",
            headers=follower_sessions[em]["headers"]
        )

# --------------------------------------------------------------------------
# EXPERIMENT 2: Margin Overdraft Race Condition (Concurrent Replication Flood)
# --------------------------------------------------------------------------
print("\n" + "=" * 50)
print("TEST 2: Margin Exhaustion Race Condition under Parallel Order Burst")
print("=" * 50)

# Set mamf1 balance to exactly $150 (Margin for 0.02 BTC is ~$128.50)
# So mamf1 can ONLY afford ONE 0.02 BTC trade. If master places 3 rapid trades,
# does mamf1 reject trades 2 and 3, or does equity plunge negative?
m_list = adm_s.get(f"{BASE_URL}/admin/api/members", headers=adm_headers).json().get("members", [])
f1_info = next((m for m in m_list if m.get("email") == "mamf1@mailinator.com"), None)
f1_id = f1_info.get("member_id")

adm_s.post(f"{BASE_URL}/admin/api/members/{f1_id}/balance", headers=adm_headers, json={"instance": "real", "balance": 150.0})

# Confirm initial funds on mamf1
r_f1_start = follower_sessions["mamf1@mailinator.com"]["session"].get(f"{BASE_URL}/v1/oms/{INSTANCE}/funds", headers=follower_sessions["mamf1@mailinator.com"]["headers"])
print(f"mamf1 Starting Balance: ${r_f1_start.json().get('funds', {}).get('balance')}")

# Master fires 3 simultaneous orders in parallel
def fire_master_order(i):
    return m_s.post(f"{BASE_URL}/v1/oms/{INSTANCE}/orders", headers=m_headers, json={
        "symbol": SYMBOL, "side": "BUY", "type": "MARKET", "qty": 0.02
    })

print("Firing 3 burst orders on Master concurrently...")
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
    m_burst_results = [f.result() for f in [ex.submit(fire_master_order, i) for i in range(3)]]

m_order_ids = [r.json().get("order", {}).get("market_order_id") for r in m_burst_results if r.status_code == 200]
print(f"Master Filled Orders: {len(m_order_ids)}")

time.sleep(3)

# Audit mamf1 funds & positions
r_f1_audit = follower_sessions["mamf1@mailinator.com"]["session"].get(f"{BASE_URL}/v1/oms/{INSTANCE}/funds", headers=follower_sessions["mamf1@mailinator.com"]["headers"])
r_f1_pos = follower_sessions["mamf1@mailinator.com"]["session"].get(f"{BASE_URL}/v1/oms/{INSTANCE}/positions", headers=follower_sessions["mamf1@mailinator.com"]["headers"])

f1_funds = r_f1_audit.json().get("funds", {})
f1_positions = r_f1_pos.json().get("positions", [])

print(f"mamf1 Positions Opened: {len(f1_positions)} (Expected max: 1 due to $150 balance)")
print(f"mamf1 Balance: ${f1_funds.get('balance'):,.2f}")
print(f"mamf1 Equity: ${f1_funds.get('equity'):,.2f}")
print(f"mamf1 Free Margin: ${f1_funds.get('free_margin'):,.2f}")
print(f"mamf1 Margin Used: ${f1_funds.get('used_margin'):,.2f}")

if f1_funds.get("free_margin") < 0:
    print("⚠️ CRITICAL DEFECT: Free margin went NEGATIVE under concurrent replication!")
elif len(f1_positions) > 1:
    print(f"⚠️ CRITICAL DEFECT: Over-leveraged! {len(f1_positions)} positions opened with only $150 capital!")
else:
    print("✅ Margin engine correctly blocked over-leveraged orders.")

# Close master burst positions
for oid in m_order_ids:
    m_s.post(f"{BASE_URL}/v1/oms/{INSTANCE}/positions/{oid}/squareoff", headers=m_headers)

time.sleep(2)

# Reset mamf1 balance to 10000000
adm_s.post(f"{BASE_URL}/admin/api/members/{f1_id}/balance", headers=adm_headers, json={"instance": "real", "balance": 10000000.0})

# --------------------------------------------------------------------------
# EXPERIMENT 3: Balance & High-Water Mark Accounting Tracking
# --------------------------------------------------------------------------
print("\n" + "=" * 50)
print("TEST 3: Ledger & High-Water Mark Accounting Drift Audit")
print("=" * 50)

# Check Master ledger and shares summary
r_m_shares = m_s.get(f"{BASE_URL}/v1/oms/{INSTANCE}/mam/shares?role=master", headers=m_headers)
print("Master Profit Shares State:", r_m_shares.status_code, r_m_shares.text[:300])

r_m_funds_final = m_s.get(f"{BASE_URL}/v1/oms/{INSTANCE}/funds", headers=m_headers)
m_final = r_m_funds_final.json().get("funds", {})
print(f"Master Final Balance: ${m_final.get('balance'):,.2f}, Equity: ${m_final.get('equity'):,.2f}")

# Check Followers balances
for em, f_data in follower_sessions.items():
    r_ff = f_data["session"].get(f"{BASE_URL}/v1/oms/{INSTANCE}/funds", headers=f_data["headers"])
    ff_funds = r_ff.json().get("funds", {})
    print(f"  {em} Balance: ${ff_funds.get('balance'):,.2f}, Equity: ${ff_funds.get('equity'):,.2f}")

print("\n" + "=" * 70)
print("🏁 AUDIT FINISHED.")
print("=" * 70)
