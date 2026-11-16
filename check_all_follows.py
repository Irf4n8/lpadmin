from dashboard_server import TraderSession
import json

s = TraderSession("mamfollower1@mailinator.com", "Test@1234", "Follower 1")
s.ensure_auth()
master_client_id = "mem_e2dbce29e1c71a7bf6"

for inst in ["paper", "real", "paper-net", "real-net"]:
    f_data = s.get_mam_follows(inst)
    print(f"=== {inst} ===")
    print(json.dumps(f_data, indent=2))

