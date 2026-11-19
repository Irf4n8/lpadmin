import json

with open("api collection/Black trader.postman_collection.json", "r", encoding="utf-8") as f:
    data = json.load(f)

def extract_details(items):
    res = []
    for it in items:
        if "item" in it:
            res.extend(extract_details(it["item"]))
        else:
            name = it.get("name", "")
            req = it.get("request", {})
            method = req.get("method", "")
            url = req.get("url", {}).get("raw", "") if isinstance(req.get("url"), dict) else str(req.get("url"))
            body = req.get("body", {}).get("raw", "") if isinstance(req.get("body"), dict) else ""
            res.append({"name": name, "method": method, "url": url, "body": body})
    return res

details = extract_details(data.get("item", []))
for d in details:
    if any(k in d["name"].lower() or k in d["url"].lower() for k in ["bulk", "order", "squareoff", "position"]):
        print(f"================ {d['name']} ================")
        print(f"METHOD: {d['method']}  URL: {d['url']}")
        if d['body']:
            print("BODY:")
            print(d['body'])
        print()
