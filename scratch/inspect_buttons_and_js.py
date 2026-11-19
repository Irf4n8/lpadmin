import re

with open('dashboard_server.py', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

# Find all buttons
buttons = re.findall(r'<button([^>]*)>(.*?)</button>', content, re.DOTALL)
print(f'Total buttons: {len(buttons)}')
for attrs, text in buttons:
    text_clean = ' '.join(text.strip().split())
    # find onclick or id
    onclick = re.search(r'onclick=["\']([^"\']+)["\']', attrs)
    btn_id = re.search(r'id=["\']([^"\']+)["\']', attrs)
    oc_val = onclick.group(1) if onclick else 'NO_ONCLICK'
    id_val = btn_id.group(1) if btn_id else 'NO_ID'
    print(f"[{id_val}] onclick: {oc_val} | text: {text_clean[:40]}")

print('\n=== JS functions defined in dashboard_server.py ===')
js_funcs = re.findall(r'function\s+([a-zA-Z0-9_]+)\s*\(([^)]*)\)', content)
for name, params in js_funcs:
    print(f"function {name}({params})")
