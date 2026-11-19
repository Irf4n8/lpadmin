import requests
import re

url = "https://lpadmin.blackfx.com/blackadmin/_next/static/chunks/pages/index-de054c4c2f902c46.js"
res = requests.get(url).text
apis = set(re.findall(r'(/admin/api/[a-zA-Z0-9_\-\/]+)', res))
print("Admin APIs found in blackadmin:")
for a in sorted(apis):
    print(" ", a)
