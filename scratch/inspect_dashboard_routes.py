with open("dashboard_server.py", "r", encoding="utf-8") as f:
    text = f.read()

import re

# find do_GET and do_POST
lines = text.split("\n")
in_post = False
in_get = False
post_lines = []
get_lines = []

for l in lines:
    if "def do_POST(" in l:
        in_post = True
        in_get = False
    elif "def do_GET(" in l:
        in_get = True
        in_post = False
    elif l.startswith("def ") or l.startswith("class "):
        in_post = False
        in_get = False
        
    if in_post and ("self.path" in l or "elif" in l or "if " in l):
        post_lines.append(l.strip())
    if in_get and ("self.path" in l or "elif" in l or "if " in l):
        get_lines.append(l.strip())

print("=== POST PATHS ===")
for p in post_lines[:40]:
    print(" ", p)

print("\n=== GET PATHS ===")
for g in get_lines[:40]:
    print(" ", g)
