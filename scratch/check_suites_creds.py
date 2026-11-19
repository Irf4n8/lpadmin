with open('dashboard/suites.py', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

import re
matches = re.findall(r'.{0,40}(?:mammaster|mamfollower|mem_e2dbce29e1c71a7bf6|12345678|mamm@mailinator.com).{0,40}', text)
for m in matches:
    print(repr(m))
