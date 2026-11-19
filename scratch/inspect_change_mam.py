with open("mam_management/change_mam_category.py", "r", encoding="utf-8") as f:
    text = f.read()

print("Length:", len(text))
lines = text.split("\n")
for l in lines[:40]:
    print(l)

