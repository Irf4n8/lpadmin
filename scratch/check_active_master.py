with open('dashboard_server.py', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'activeMasterId' in line:
        print(f"Line {i+1}: {line.strip()}")
