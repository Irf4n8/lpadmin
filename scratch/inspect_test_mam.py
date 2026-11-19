with open("test_mam.py", "r", encoding="utf-8") as f:
    text = f.read()

funcs = [line.strip() for line in text.split("\n") if line.strip().startswith("def ") or line.strip().startswith("class ")]
for fn in funcs:
    print(fn)

