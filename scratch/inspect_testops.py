with open('dashboard_server.py', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'def _testops_get' in line:
        print(f"_testops_get found at line {i+1}")
        for j in range(i, min(i+100, len(lines))):
            print(f"{j+1}: {lines[j]}", end='')
        break
