import json

with open(r"c:\Users\hp\Downloads\Black trader.postman_collection.json", "r", encoding="utf-8") as f:
    col = json.load(f)

print("Collection variables:")
for v in col.get("variable", []):
    print(f"  {v.get('key')}: {v.get('value')}")
