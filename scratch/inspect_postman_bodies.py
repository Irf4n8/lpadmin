import json

with open(r"c:\Users\hp\Downloads\Black trader.postman_collection.json", "r", encoding="utf-8") as f:
    col = json.load(f)

for it in col.get("item", []):
    name = it.get("name", "")
    req = it.get("request", {})
    method = req.get("method", "")
    url = req.get("url", {}).get("raw", "") if isinstance(req.get("url"), dict) else str(req.get("url"))
    body = req.get("body", {}).get("raw", "") if isinstance(req.get("body"), dict) else ""
    print(f"=== {name} ===")
    print(f"{method} {url}")
    if body:
        print(f"Body:\n{body}")
    print()
