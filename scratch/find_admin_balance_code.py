import requests
import re

r = requests.get('https://lpadmin.blackfx.com/blackadmin')
scripts = re.findall(r'src="([^"]+)"', r.text)
print("Found scripts:", len(scripts))

chunks_with_balance = []
for s in scripts:
    url = f"https://lpadmin.blackfx.com{s}" if s.startswith('/') else s
    res = requests.get(url)
    if "balance" in res.text.lower():
        chunks_with_balance.append(url)
        # find snippets with balance and member
        matches = re.findall(r'.{0,50}balance.{0,50}', res.text, re.IGNORECASE)
        print(f"\nChunk: {url}")
        for m in matches[:5]:
            print("  ->", m.strip())
