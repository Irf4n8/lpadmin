import requests, re

r = requests.get('https://lpadmin.blackfx.com/assets/app.js')
print("app.js length:", len(r.text))
with open("app_js_dump.js", "w", encoding="utf-8") as f:
    f.write(r.text)

endpoints = re.findall(r'/(?:api|admin|v1|oms)/[a-zA-Z0-9_\-\/{}:]+', r.text)
print("Unique API endpoints found in app.js:", len(set(endpoints)))
for ep in sorted(list(set(endpoints)))[:30]:
    print(" ", ep)

