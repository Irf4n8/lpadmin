import re

with open('dashboard_server.py', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

print('=== Searching for fetch / $.ajax / endpoints in JS ===')
endpoints = set(re.findall(r'fetch\(["\'`](/[^"\'`?]+)', content))
for ep in sorted(endpoints):
    print('JS fetch endpoint:', ep)

print('\n=== Searching for path matches in backend ===')
matches = re.findall(r'(?:if|elif)\s+(?:path|self\.path)\s*==\s*["\']([^"\']+)["\']', content)
for pm in sorted(set(matches)):
    print('Route match:', pm)

print('\n=== Searching for testops methods ===')
for m in re.finditer(r'def _testops[a-zA-Z0-9_]*', content):
    print(m.group(0))

print('\n=== Searching for any button tags or onclick ===')
buttons = re.findall(r'<button[^>]*>.*?</button>', content, re.DOTALL)
print(f'Total buttons found in HTML: {len(buttons)}')
for b in buttons[:20]:
    # print one line summary
    b_clean = ' '.join(b.split())
    if len(b_clean) > 100:
        b_clean = b_clean[:100] + '...'
    print('Button:', b_clean)
