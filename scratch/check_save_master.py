with open('dashboard_server.py', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'function saveMasterMAMSettings' in line or 'saveMasterMAMSettings' in line:
        print(f"Line {i+1}: {line}")
        for j in range(max(0, i-5), min(i+45, len(lines))):
            print(f"{j+1}: {lines[j]}", end='')
        break
