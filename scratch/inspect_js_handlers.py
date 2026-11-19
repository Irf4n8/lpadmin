with open('dashboard_server.py', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

import re

# find <script> ... </script>
scripts = re.findall(r'<script>(.*?)</script>', content, re.DOTALL)
print(f"Total script blocks: {len(scripts)}")
js = scripts[0] if scripts else ""
print(f"JS length: {len(js)}")

# Search for button event handlers or functions like applyFleet, saveMaster, etc.
functions_to_check = [
    'saveMasterMAMSettings',
    'applyFleetCategory',
    'applyFleetBulkFollow',
    'applyFleetUnfollow',
    'applyFleetBrokerToggle',
    'applyFleetBalance',
    'applyFleetBook',
    'saveQuickManageCategory',
    'quickManageLeaveMaster',
    'saveQuickManageBook',
    'quickManageToggleBroker',
    'saveQuickManageBalance',
    'switchEnvironment'
]

for fn in functions_to_check:
    match = re.search(r'function\s+' + fn + r'\s*\([^)]*\)\s*\{.*?(?=\n\s*function|\n\s*</script>|\Z)', js, re.DOTALL)
    if match:
        print(f"\n==================== {fn} ====================")
        lines = match.group(0).split('\n')
        for l in lines[:40]:
            print(l)
        if len(lines) > 40:
            print(f"... ({len(lines)-40} more lines)")
