import sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from test_suite.client import BlackTraderClient

client = BlackTraderClient()
admin_tok = client.get_admin_token()
print("Admin token obtained:", bool(admin_tok))

master_tok = client.get_trader_token("mammaster@mailinator.com", "Test@1234")
print("Master token obtained:", bool(master_tok))

headers = {"Authorization": f"Bearer {master_tok}"}

# Check master funds
for inst in ["real", "paper"]:
    r = client.request_with_retry("GET", f"https://lpadmin.blackfx.com/v1/oms/{inst}/funds", headers=headers)
    print(f"Master {inst} funds: {r.status_code}", r.json() if r.status_code == 200 else r.text)

# Check master mam/masters or mam/follows
for inst in ["real", "paper"]:
    r = client.request_with_retry("GET", f"https://lpadmin.blackfx.com/v1/oms/{inst}/mam/follows", headers=headers)
    print(f"Master {inst} mam follows: {r.status_code}", r.json() if r.status_code == 200 else r.text)
