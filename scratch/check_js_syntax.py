with open('dashboard_server.py', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

import re

# find <script> ... </script>
scripts = re.findall(r'<script>(.*?)</script>', content, re.DOTALL)
js = scripts[0]

# find every function definition and check if it uses await inside
func_defs = list(re.finditer(r'(async\s+)?function\s+([a-zA-Z0-9_]+)\s*\(([^)]*)\)\s*\{', js))

for i, m in enumerate(func_defs):
    is_async = bool(m.group(1))
    name = m.group(2)
    start_pos = m.end()
    # find where this function ends (or next function starts)
    next_pos = func_defs[i+1].start() if i+1 < len(func_defs) else len(js)
    body = js[start_pos:next_pos]
    has_await = bool(re.search(r'\bawait\b', body))
    if has_await and not is_async:
        print(f"CRITICAL SYNTAX ERROR: function {name}() uses 'await' but is NOT marked 'async'!")
    elif is_async and not has_await:
        # harmless
        pass
