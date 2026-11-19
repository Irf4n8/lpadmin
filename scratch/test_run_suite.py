import sys
sys.path.insert(0, '.')
from dashboard import testops

# check what run_suite accepts
print("Testing testops.run_suite validation with bad suite:")
res, status = testops.run_suite({"suite": "unknown"})
print("Response:", status, res)
