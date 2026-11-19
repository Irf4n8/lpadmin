import json

with open("api collection/lpadmin.postman_environment.json", "r", encoding="utf-8") as f:
    env = json.load(f)

print("=== ENVIRONMENT VARIABLES ===")
for val in env.get("values", []):
    if val.get("enabled", True):
        k = val.get("key")
        v = str(val.get("value"))
        if len(v) > 60:
            v = v[:57] + "..."
        print(f"  {k}: {v}")

with open("api collection/lpadmin.postman_collection.json", "r", encoding="utf-8") as f:
    coll = json.load(f)

print("\n=== POSTMAN COLLECTION INFO ===")
print("Name:", coll.get("info", {}).get("name"))
print("Description:", coll.get("info", {}).get("description"))

def list_folders(items, prefix=""):
    for item in items:
        name = item.get("name", "")
        if "item" in item:
            print(f"{prefix}📁 {name} ({len(item['item'])} items)")
            list_folders(item["item"], prefix + "  ")
        else:
            req = item.get("request", {})
            method = req.get("method", "GET")
            url = req.get("url", {})
            if isinstance(url, dict):
                raw_url = url.get("raw", "")
            else:
                raw_url = str(url)
            # print only first 5 items per level or summarize
            pass

print("\n=== TOP LEVEL FOLDERS / ITEMS ===")
for item in coll.get("item", []):
    name = item.get("name", "")
    if "item" in item:
        print(f"📁 {name} ({len(item['item'])} items)")
    else:
        req = item.get("request", {})
        print(f"📄 {name} [{req.get('method')}]")
