import sys, os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from test_suite.client import BlackTraderClient

client = BlackTraderClient()
admin_tok = client.get_admin_token()
members = client.get_admin_members()
print(f"Total members on platform: {len(members)}")

emails = [m.get("email") for m in members]
print("mamm@mailinator.com exists?", "mamm@mailinator.com" in emails)
mamf_exist = [f"mamf{i}@mailinator.com" in emails for i in range(1, 101)]
print(f"mamf1..100 exist count: {sum(mamf_exist)}/100")
