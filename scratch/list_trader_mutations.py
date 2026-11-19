import json

with open("scratch/all_endpoints.json") as f:
    eps = json.load(f)

trader_mut = [e for e in eps if e["folder"].startswith("Trader API") and e["method"] in ["POST", "PUT", "DELETE"]]
print(f"Total Trader mutations: {len(trader_mut)}")
for e in trader_mut:
    print(f"[{e['method']}] {e['folder']} -> {e['name']} ({e['url']})")
