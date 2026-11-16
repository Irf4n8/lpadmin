import requests

text = requests.get("https://chartv2.blacktrader.com/assets/index-BCdMHPbx.js").text

idx = 0
for term in ["ticket-brokers", "getActiveBrokers", "resolveBrokers"]:
    idx = text.find(term)
    while idx != -1:
        print(f"=== {term} at {idx} ===")
        print(text[max(0, idx-100):min(len(text), idx+300)])
        print("-" * 50)
        idx = text.find(term, idx + len(term))

import urllib.request
import re

c_url = "https://chartv2.blacktrader.com/assets/tradeApp-BaiBL75n.js"
req = urllib.request.Request(c_url, headers={'User-Agent': 'Mozilla/5.0'})
txt = urllib.request.urlopen(req).read().decode("utf-8", errors="ignore")

for m in re.finditer(r"toggleBrokerActive", txt):
    start = max(0, m.start() - 100)
    end = min(len(txt), m.end() + 200)
    print("toggleBrokerActive:", txt[start:end])
