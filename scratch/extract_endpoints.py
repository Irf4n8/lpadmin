import json

with open("api collection/lpadmin.postman_collection.json", "r", encoding="utf-8") as f:
    coll = json.load(f)

endpoints = []

def extract(items, folder_path=""):
    for item in items:
        name = item.get("name", "")
        if "item" in item:
            extract(item["item"], f"{folder_path}/{name}" if folder_path else name)
        else:
            req = item.get("request", {})
            method = req.get("method", "GET")
            url = req.get("url", {})
            raw_url = url.get("raw", "") if isinstance(url, dict) else str(url)
            endpoints.append({
                "folder": folder_path,
                "name": name,
                "method": method,
                "url": raw_url,
                "body": req.get("body", {}).get("raw", "") if "body" in req else None
            })

extract(coll.get("item", []))
print(f"Total endpoints extracted: {len(endpoints)}")

with open("scratch/all_endpoints.json", "w") as f:
    json.dump(endpoints, f, indent=2)

# Print mutating endpoints
mutating = [ep for ep in endpoints if ep["method"] in ["POST", "PUT", "DELETE"]]
print(f"Total mutating endpoints: {len(mutating)}")
for ep in mutating[:40]:
    print(f"[{ep['method']}] {ep['folder']} -> {ep['name']} ({ep['url']})")
