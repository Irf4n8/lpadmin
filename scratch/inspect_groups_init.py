with open('dashboard_server.py', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

for i in range(40, 100):
    print(f"{i+1}: {lines[i]}", end='')
