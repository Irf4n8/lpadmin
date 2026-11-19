with open('dashboard_server.py', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

for j in range(4798, min(4879, len(lines))):
    print(f"{j+1}: {lines[j]}", end='')
