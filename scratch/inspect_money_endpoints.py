import json

with open("scratch/all_endpoints.json") as f:
    eps = json.load(f)

for e in eps:
    if any(k in e["url"] for k in ["wallets", "portal", "transfers", "deposits", "withdrawals"]):
        print(f"[{e['method']}] {e['name']} ({e['url']})")
        if e.get("body"):
            print("  BODY:", e["body"])
