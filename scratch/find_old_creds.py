with open('dashboard_server.py', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

import re

for i, line in enumerate(lines):
    if 'mamfollower' in line or 'mammaster' in line or 'Test@1234' in line or 'mem_e2dbce29e1c71a7bf6' in line:
        print(f"Line {i+1}: {line.strip()}")
