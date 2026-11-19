import requests
import time

BASE_URL = 'https://lpadmin.blackfx.com'
s_adm = requests.Session()
r_adm = s_adm.post(f'{BASE_URL}/admin/api/login', json={'email': 'lpadmin@blacktrader.com', 'password': 'Raj1234!'})
t_adm = r_adm.json().get('token')
h_adm = {'Authorization': f'Bearer {t_adm}', 'Content-Type': 'application/json'}

# Get mamf99 info
m_list = s_adm.get(f'{BASE_URL}/admin/api/members', headers=h_adm).json().get('members', [])
f99 = next(m for m in m_list if m.get('email') == 'mamf99@mailinator.com')
f99_id = f99.get('member_id')

# Set mamf99 balance to exactly $0.00
s_adm.post(f'{BASE_URL}/admin/api/members/{f99_id}/balance', headers=h_adm, json={'instance': 'real', 'balance': 0.0})

# Follower login
s_f = requests.Session()
s_f.post(f'{BASE_URL}/api/auth/login', json={'email': 'mamf99@mailinator.com', 'password': '12345678'})
t_f = s_f.post(f'{BASE_URL}/api/auth/chart-token').json().get('token')
h_f = {'Authorization': f'Bearer {t_f}', 'Content-Type': 'application/json'}

# Follow Master
s_f.post(f'{BASE_URL}/v1/oms/real/mam/follow', headers=h_f, json={
    'master_client_id': 'mem_11434b0b9d9d210899', 'method': 'multiplier', 'multiplier': 1.0, 'share_percent': 50.0
})

# Master login
s_m = requests.Session()
s_m.post(f'{BASE_URL}/api/auth/login', json={'email': 'mamm@mailinator.com', 'password': '12345678'})
t_m = s_m.post(f'{BASE_URL}/api/auth/chart-token').json().get('token')
h_m = {'Authorization': f'Bearer {t_m}', 'Content-Type': 'application/json'}

# Master places order
r_ord = s_m.post(f'{BASE_URL}/v1/oms/real/orders', headers=h_m, json={
    'symbol': 'BINANCE:BTCUSDT', 'side': 'BUY', 'type': 'MARKET', 'qty': 0.01
})
m_ord_id = r_ord.json().get('order', {}).get('market_order_id')
print('Master Order ID:', m_ord_id)
time.sleep(2)

# Check mamf99 positions
r_pos = s_f.get(f'{BASE_URL}/v1/oms/real/positions', headers=h_f)
pos_list = r_pos.json().get('positions', [])
r_funds = s_f.get(f'{BASE_URL}/v1/oms/real/funds', headers=h_f)
funds = r_funds.json().get('funds', {})

print('Follower Positions Count:', len(pos_list))
print('Follower Funds:', funds)

# Cleanup
if m_ord_id:
    s_m.post(f'{BASE_URL}/v1/oms/real/positions/{m_ord_id}/squareoff', headers=h_m)
for p in pos_list:
    m_id = p.get('market_order_id')
    if m_id:
        s_f.post(f'{BASE_URL}/v1/oms/real/positions/{m_id}/squareoff', headers=h_f)
s_adm.post(f'{BASE_URL}/admin/api/members/{f99_id}/balance', headers=h_adm, json={'instance': 'real', 'balance': 10000000.0})
print('Test & Cleanup completed.')
