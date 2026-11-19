with open('dashboard_server.py', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'def update_mam_master_settings' in line:
        print(f"Line {i+1}:")
        for j in range(i, min(i+40, len(lines))):
            print(f"{j+1}: {lines[j]}", end='')
