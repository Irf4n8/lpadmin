with open('dashboard_server.py', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

import re
matches = re.findall(r'.{0,50}(?:mamfollower|mammaster|mem_e2dbce29e1c71a7bf6).{0,50}', text)
for m in matches:
    print(repr(m))
