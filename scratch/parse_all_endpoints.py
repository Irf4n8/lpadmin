with open("scratch/api_reference_dump.txt", "r", encoding="utf-8") as f:
    text = f.read()

lines = text.split("\n")
print(f"Total lines: {len(lines)}")

# Let's find headings and endpoints
current_group = ""
endpoints = []
for i, line in enumerate(lines):
    line_s = line.strip()
    if line_s in ["Authentication", "Accounts & venues", "Orders", "Positions", "Account & funds", 
                  "Streams", "Market signals and alerts", "Instance", "Wallets", "Client portal", 
                  "IB", "Copy trading", "MAM", "PAMM", "AI assistant", "Catalogue"]:
        current_group = line_s
    elif line_s.startswith("/oms/"):
        method = lines[i-2].strip() if i >= 2 else ""
        desc = lines[i-1].strip() if i >= 1 else ""
        endpoints.append((current_group, method, line_s, desc))

print(f"Extracted {len(endpoints)} endpoints:")
for group, method, path, desc in endpoints:
    print(f"[{group:15}] {method:6} {path:40} : {desc}")

