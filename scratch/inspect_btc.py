with open("bug_inducing_test_cases/run_bug_suite.py", "r", encoding="utf-8") as f:
    text = f.read()

lines = text.split("\n")
for i, l in enumerate(lines):
    if '"id": "BTC' in l or '"title":' in l:
        print(l.strip())

