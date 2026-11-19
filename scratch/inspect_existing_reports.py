import os

print("=== BUG INDUCING TEST CASE REPORTS ===")
for i in range(1, 11):
    path = f"bug_inducing_test_cases/reports/BTC{i:02d}_report.md"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f.readlines() if line.strip()]
            print(f"\n--- BTC{i:02d} ---")
            print("\n".join(lines[:6]))

print("\n=== COMPLEX TEST CASE REPORTS ===")
for i in range(1, 11):
    path = f"complex_test_cases/reports/CTC{i:02d}_report.md"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f.readlines() if line.strip()]
            print(f"\n--- CTC{i:02d} ---")
            print("\n".join(lines[:6]))

