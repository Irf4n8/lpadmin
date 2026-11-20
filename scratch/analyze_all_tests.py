import json

with open('scratch/all_165_scenarios.json') as f:
    scenarios = json.load(f)

for i in range(0, 165, 15):
    s = scenarios[i]
    print(f"{s['id']} ({s['module']}): {s['title']}")
