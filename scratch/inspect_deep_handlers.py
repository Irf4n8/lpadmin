with open('dashboard_server.py', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

print("Inspecting lines 650 to 1150:")
for i in range(650, 1150):
    if i < len(lines):
        line = lines[i]
        # print if it defines a method or has interesting logic
        if line.strip().startswith("def ") or "mamfollower" in line or "client_id" in line or "ADMIN_" in line or "requests." in line or "url =" in line:
            print(f"{i+1}: {line.strip()}")
