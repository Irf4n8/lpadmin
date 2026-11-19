import requests

res = requests.post("http://localhost:8500/api/manage/category", json={
    "target_type": "range",
    "start": 1,
    "end": 5,
    "category": "multiplier",
    "multiplier": 1.5,
    "share_percent": 50.0
})
print("Category response:", res.status_code, res.text)
