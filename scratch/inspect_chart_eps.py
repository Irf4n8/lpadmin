import json

with open("scratch/all_endpoints.json") as f:
    eps = json.load(f)

chart_eps = [e for e in eps if "Chart" in e["folder"] or "chart" in e["url"]]
print(f"Total Chart endpoints: {len(chart_eps)}")
for e in chart_eps:
    print(f"[{e['method']}] {e['folder']} -> {e['name']} ({e['url']})")
