import json
from datetime import datetime

with open("scratch/btc07_follower_audit.json") as f:
    data = json.load(f)

m_trades = data["master_trades"]
f_trades = data["follower_trades"]

def parse_dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))

print(f"Total Master Trades: {len(m_trades)}")
print(f"Total Follower Trades: {len(f_trades)}")

for mt in m_trades:
    hid = mt["history_id"]
    m_exit_dt = parse_dt(mt["executed_at"])
    m_ep = mt["exit_price"]
    matching_f = [f for f in f_trades if f["exit_price"] == m_ep]
    latencies = [(parse_dt(f["executed_at"]) - m_exit_dt).total_seconds() for f in matching_f]
    print(f"\n--- Master Trade #{hid} ---")
    print(f"Master Exit Time:  {mt['executed_at']}")
    print(f"Master Exit Price: {m_ep}")
    print(f"Followers Replicated & Closed: {len(matching_f)}")
    print(f"Min Latency from Master: {min(latencies)*1000:.2f} ms")
    print(f"Max Latency from Master: {max(latencies)*1000:.2f} ms")
    print(f"Avg Latency from Master: {(sum(latencies)/len(latencies))*1000:.2f} ms")

    # Verify if all follower exit prices match master exactly
    unique_follower_prices = set(f["exit_price"] for f in matching_f)
    print(f"Unique Follower Exit Prices: {unique_follower_prices} (Matches Master: {unique_follower_prices == {m_ep}})")
