import json

with open("scratch/key_api_docs.json", "r", encoding="utf-8") as f:
    docs = json.load(f)

for k, v in docs.items():
    print(f"==================== {k} ====================")
    lines = v.split("\n")
    print("\n".join(lines[:30]))
    print("\n")

