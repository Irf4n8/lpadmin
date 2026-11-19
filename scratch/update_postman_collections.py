import json

for path in [
    r"c:\Users\hp\Downloads\BlackTrader Testing\BlackTrader Testing-20261112T041830Z-1-001\BlackTrader Testing\api collection\Black trader.postman_collection.json",
    r"c:\Users\hp\Downloads\Black trader.postman_collection.json"
]:
    with open(path, "r", encoding="utf-8") as f:
        col = json.load(f)
    
    # Update variables
    for v in col.get("variable", []):
        if v.get("key") == "email":
            v["value"] = "mamm@mailinator.com"
        elif v.get("key") == "password":
            v["value"] = "12345678"
            
    with open(path, "w", encoding="utf-8") as f:
        json.dump(col, f, indent=2)
    print("Updated", path)
