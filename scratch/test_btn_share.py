import requests

res = requests.post("http://localhost:8500/api/manage/master-share", json={
    "master_id": "mam",
    "share_percent": 50.0,
    "display_name": "mamm"
})
print("Master share response:", res.status_code, res.text)
