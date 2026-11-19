with open('dashboard_server.py', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

marker = "  <script>\n    let activeTab"
marker2 = "<script>\n    let activeTab"
print("marker in content:", marker in content)
print("marker2 in content:", marker2 in content)

import re
m = re.search(r'<script>[^<]*let activeTab', content)
if m:
    print("Found script let activeTab:", repr(m.group(0)))
else:
    print("Pattern not found!")
