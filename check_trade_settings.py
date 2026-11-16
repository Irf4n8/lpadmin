import urllib.request
import re

req = urllib.request.Request("https://chartv2.blacktrader.com/assets/tradeSettings-wYh18qZ8.js", headers={'User-Agent': 'Mozilla/5.0'})
content = urllib.request.urlopen(req).read().decode("utf-8", errors="ignore")

print("File tradeSettings size:", len(content))
for m in re.finditer(r"broker", content, re.IGNORECASE):
    start = max(0, m.start() - 100)
    end = min(len(content), m.end() + 150)
    print(content[start:end])
    print("-" * 40)

