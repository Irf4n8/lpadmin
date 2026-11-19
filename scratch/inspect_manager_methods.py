with open('dashboard_server.py', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

import re

# Find all occurrences of handle_ in MultiMasterDashboardManager
methods = re.findall(r'def (handle_[a-zA-Z0-9_]+)\(self[^)]*\):', content)
print('Manager handle methods:', methods)

# Let's inspect the definitions of each handle method
for m in methods:
    match = re.search(r'def ' + m + r'\(self.*?(?=\n    def |\nclass |\Z)', content, re.DOTALL)
    if match:
        print(f"\n--- Method: {m} ---")
        lines = match.group(0).split('\n')
        for l in lines[:30]:
            print(l)
        if len(lines) > 30:
            print(f"... ({len(lines) - 30} more lines)")
