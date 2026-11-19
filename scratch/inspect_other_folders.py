import json

with open("scratch/all_endpoints.json") as f:
    eps = json.load(f)

for e in eps:
    if any(k in e["folder"] for k in ["PAMM", "Copy trading", "IB", "venues", "Overview", "OMS", "staff", "groups"]):
        print(f"[{e['method']}] {e['folder']} -> {e['name']} ({e['url']})")
