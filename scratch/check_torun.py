with open('dashboard/mam_testops_panel.html', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'function toRun' in line or 'toRun(' in line:
        print(f"Line {i+1}:")
        for j in range(max(0, i-5), min(i+40, len(lines))):
            print(f"{j+1}: {lines[j]}", end='')
        break
