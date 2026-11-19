with open('dashboard/testops.py', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

print("Lines in dashboard/testops.py:", len(lines))
for i, line in enumerate(lines[:60]):
    print(f"{i+1}: {line}", end='')
