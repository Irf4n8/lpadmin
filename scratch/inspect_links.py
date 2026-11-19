import json

with open("scratch/api_reference_links.json", "r", encoding="utf-8") as f:
    links = json.load(f)

print(f"Total links: {len(links)}")
for l in links:
    if any(k in l["href"].lower() for k in ["mam", "copy", "pamm", "order", "position", "funds"]):
        print(f"{l['href']:30} : {l['text']}")

