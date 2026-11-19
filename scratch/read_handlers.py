with open('dashboard_server.py', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'def handle_category_change' in line:
        print(f"Line {i+1}:")
        for j in range(max(0, i-50), min(len(lines), i+250)):
            print(f"{j+1}: {lines[j]}", end='')
        break
