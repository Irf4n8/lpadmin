with open('dashboard/mam_testops_panel.html', 'r', encoding='utf-8', errors='ignore') as f:
    panel_content = f.read()

import re
buttons = re.findall(r'<button[^>]*>.*?</button>', panel_content, re.DOTALL)
print(f"Buttons in mam_testops_panel.html: {len(buttons)}")
for b in buttons:
    print(' '.join(b.split()))

print("\n--- Any fetch calls in panel? ---")
fetches = re.findall(r'fetch\([^\)]+\)', panel_content)
for fc in fetches:
    print(fc)
