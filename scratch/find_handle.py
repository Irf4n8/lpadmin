with open('dashboard_server.py', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

import re
matches = [m.start() for m in re.finditer(r'handle_category_change', content)]
print(f"Matches for handle_category_change: {len(matches)}")
for idx in matches:
    start = max(0, idx - 100)
    end = min(len(content), idx + 200)
    print(content[start:end])
    print("="*40)
