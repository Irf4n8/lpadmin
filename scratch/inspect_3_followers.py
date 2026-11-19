import requests

BASE_URL = 'https://lpadmin.blackfx.com'
s_adm = requests.Session()
r_adm = s_adm.post(f'{BASE_URL}/admin/api/login', json={'email': 'lpadmin@blacktrader.com', 'password': 'Raj1234!'})
t_adm = r_adm.json().get('token')
h_adm = {'Authorization': f'Bearer {t_adm}', 'Content-Type': 'application/json'}

m_list = s_adm.get(f'{BASE_URL}/admin/api/members', headers=h_adm).json().get('members', [])
id_map = {m.get('member_id'): m.get('email') for m in m_list}

f_ids = ['mem_11434b0b9d9d210899', 'mem_0ea679062ffd38adf7', 'mem_761e39f83d27137624', 'mem_87cc39bb4ddf52a026']

for fid in f_ids:
    email = id_map.get(fid)
    s = requests.Session()
    s.post(f'{BASE_URL}/api/auth/login', json={'email': email, 'password': '12345678'})
    tok = s.post(f'{BASE_URL}/api/auth/chart-token').json().get('token')
    h = {'Authorization': f'Bearer {tok}', 'Content-Type': 'application/json'}
    funds = s.get(f'{BASE_URL}/v1/oms/real/funds', headers=h).json().get('funds', {})
    pos = s.get(f'{BASE_URL}/v1/oms/real/positions', headers=h).json().get('positions', [])
    print(f'Member: {email} ({fid})')
    print(f'  Balance: {funds.get("balance")}, Equity: {funds.get("equity")}, Free Margin: {funds.get("free_margin")}, Used Margin: {funds.get("used_margin")}')
    print(f'  Positions: {len(pos)}')
    for p in pos:
        print(f'    Pos: {p.get("symbol")} {p.get("side")} Qty: {p.get("net_qty")} PnL: {p.get("unrealized_pnl")}')
