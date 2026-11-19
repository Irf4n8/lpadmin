import requests

res = requests.post("http://localhost:8500/api/manage/environment", json={"instance": "real"})
print("Environment switch response:", res.status_code, res.text)
