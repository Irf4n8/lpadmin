import json

with open("api collection/lpadmin.postman_collection.json", "r", encoding="utf-8") as f:
    coll = json.load(f)

def print_tree(items, indent=0):
    for item in items:
        name = item.get("name", "")
        if "item" in item:
            print("  " * indent + f"📁 {name} ({len(item['item'])})")
            print_tree(item["item"], indent + 1)
        else:
            req = item.get("request", {})
            method = req.get("method", "GET")
            url = req.get("url", {})
            raw_url = url.get("raw", "") if isinstance(url, dict) else str(url)
            # print("  " * indent + f"  [{method}] {name} -> {raw_url}")

print_tree(coll.get("item", []))
