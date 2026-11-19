with open('dashboard_server.py', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'def _authorized' in line:
        print(f"_authorized found at line {i+1}")
        for j in range(max(0, i-10), min(i+40, len(lines))):
            print(f"{j+1}: {lines[j]}", end='')
        break
