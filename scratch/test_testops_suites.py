from dashboard import testops

res, code = testops.get_suites()
print("Suites count:", len(res.get("suites", [])))
for s in res.get("suites", [])[:3]:
    print("Suite:", s)
