import requests

CREDS = [
    ("mamm@mailinator.com", "12345678"),
    ("mamf1@mailinator.com", "12345678"),
    ("mamf2@mailinator.com", "12345678"),
    ("mamf3@mailinator.com", "12345678")
]

print("=== ACCOUNT STATUS AUDIT ===")
for email, pwd in CREDS:
    s = requests.Session()
    r = s.post("https://lpadmin.blackfx.com/api/auth/login", json={"email": email, "password": pwd})
    if r.status_code == 200:
        token = r.json().get("token") or r.cookies.get("token")
        s.headers["Authorization"] = f"Bearer {token}"
        
        # Get accounts / balance
        r_acc = s.get("https://lpadmin.blackfx.com/api/accounts")
        accounts = r_acc.json() if r_acc.status_code == 200 else []
        
        # Get positions
        r_pos = s.get("https://lpadmin.blackfx.com/api/positions")
        positions = r_pos.json() if r_pos.status_code == 200 else []
        
        print(f"\nUser: {email}")
        for a in accounts:
            print(f"  Account {a.get('id')}: type={a.get('type')}, balance={a.get('balance')}, equity={a.get('equity')}, free_margin={a.get('free_margin')}")
        print(f"  Open positions: {len(positions)}")
        for p in positions:
            print(f"    Pos {p.get('id')}: sym={p.get('symbol')}, side={p.get('side')}, lots={p.get('lots')}, pnl={p.get('pnl')}")
    else:
        print(f"Failed to login {email}: {r.status_code}")
