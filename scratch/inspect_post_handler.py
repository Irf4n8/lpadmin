with open('dashboard_server.py', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

print('Total lines in dashboard_server.py:', len(lines))

for i, line in enumerate(lines):
    if 'def do_POST' in line:
        print(f"do_POST found at line {i+1}")
        for j in range(i, min(i+150, len(lines))):
            print(f"{j+1}: {lines[j]}", end='')
        break
