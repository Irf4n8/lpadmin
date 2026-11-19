import json

with open(r"c:\Users\hp\Downloads\Black trader.postman_collection.json", "r", encoding="utf-8") as f:
    col = json.load(f)

def list_folders(items, prefix=""):
    for it in items:
        name = it.get("name", "")
        if "item" in it:
            print(f"{prefix}[FOLDER] {name} ({len(it['item'])} items)")
            list_folders(it["item"], prefix + "  ")
        else:
            req = it.get("request", {})
            method = req.get("method", "")
            url = req.get("url", {}).get("raw", "") if isinstance(req.get("url"), dict) else str(req.get("url"))
            print(f"{prefix}{method:6} {url:60} : {name}")

list_folders(col.get("item", []))
