import requests

res = requests.post("http://localhost:8500/api/manage/book", json={
    "target_type": "single",
    "single_email": "mamf1@mailinator.com",
    "book": "b"
})
print("Book response:", res.status_code, res.text)
