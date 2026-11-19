with open('dashboard_server.py', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

import re

# Find all tabs
tab_buttons = re.findall(r'<button[^>]*switchTab\([^)]*\)[^>]*>.*?</button>', content, re.DOTALL)
for tb in tab_buttons:
    print('Tab button:', ' '.join(tb.split()))

# Find tab contents
tab_panes = re.findall(r'<div[^>]*class=["\'][^"\']*tab-content[^"\']*["\'][^>]*id=["\']([^"\']+)["\']', content)
print('Tab panes:', tab_panes)

# Also search for "testops" or "suite" or "run" in the HTML/JS
testops_html = re.findall(r'.{0,40}(?:testops|suite|btn-run|run-btn).{0,40}', content, re.IGNORECASE)
print(f'Testops mentions in content: {len(testops_html)}')
for th in testops_html[:10]:
    print(' ', repr(th))
