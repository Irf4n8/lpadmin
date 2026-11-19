with open('dashboard_server.py', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if any(k in line for k in ['mamfollower', 'mammaster', 'mem_e2dbce29e1c71a7bf6', 'follower_prefix', 'follower_domain']):
        print(f"{i+1}: {line.strip()}")
