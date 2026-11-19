import os
import sys
sys.path.insert(0, os.path.abspath("."))
import json
import concurrent.futures
from datetime import datetime
from dashboard_server import TraderSession

def check_follower(i):
    email = f"mamfollower{i}@mailinator.com"
    ts = TraderSession(email, "Test@1234", f"F{i}")
    if not ts.authenticate():
        return (i, "auth_fail", [])
    h = ts.get_history("paper")
    matched = [x for x in h if "2026-11-12T10:45:" in (x.get("executed_at") or "")]
    return (i, "ok", matched)

def main():
    print("Fetching master trade history...")
    m = TraderSession("mammaster@mailinator.com", "Test@1234", "Master")
    m.authenticate()
    m_hist = m.get_history("paper")
    m_matched = [x for x in m_hist if "2026-11-12T10:45:" in (x.get("executed_at") or "")]
    print(f"Master BTC07 Trades ({len(m_matched)} trades):")
    for t in m_matched:
        print(f"  ID: {t.get('history_id')}, Qty: {t.get('qty')}, Opened: {t.get('opened_at')}, Exit: {t.get('executed_at')}, EntryP: {t.get('entry_price')}, ExitP: {t.get('exit_price')}")

    print("\nFetching history for 100 followers in parallel...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=25) as ex:
        results = list(ex.map(check_follower, range(1, 101)))

    all_matched = {}
    for i, status, trades in sorted(results, key=lambda x: x[0]):
        if trades:
            all_matched[i] = trades

    print(f"\nFollowers with BTC07 trades found: {len(all_matched)} / 100")

    # Analyze exit times and exit prices
    exit_times = []
    exit_prices = []
    
    follower_details = []

    for i in sorted(all_matched.keys()):
        trades = all_matched[i]
        for t in trades:
            et = t.get("executed_at")
            ep = float(t.get("exit_price") or 0)
            qty = t.get("qty")
            hist_id = t.get("history_id")
            exit_times.append(et)
            exit_prices.append(ep)
            follower_details.append({
                "follower": i,
                "history_id": hist_id,
                "qty": qty,
                "opened_at": t.get("opened_at"),
                "executed_at": et,
                "entry_price": t.get("entry_price"),
                "exit_price": ep
            })

    if exit_times:
        min_exit = min(exit_times)
        max_exit = max(exit_times)
        min_price = min(exit_prices)
        max_price = max(exit_prices)
        unique_prices = set(exit_prices)
        print(f"\n=== Telemetry Analysis ===")
        print(f"Total follower trades: {len(follower_details)}")
        print(f"Earliest Follower Exit Time: {min_exit}")
        print(f"Latest Follower Exit Time:   {max_exit}")
        
        # Calculate time span
        t1 = datetime.fromisoformat(min_exit.replace("Z", "+00:00"))
        t2 = datetime.fromisoformat(max_exit.replace("Z", "+00:00"))
        diff_sec = (t2 - t1).total_seconds()
        print(f"Spread between first and last follower exit: {diff_sec:.3f} seconds")

        print(f"\nExit Price Min: {min_price}")
        print(f"Exit Price Max: {max_price}")
        print(f"Unique Exit Prices: {unique_prices}")
        print(f"Master Exit Prices: {[t.get('exit_price') for t in m_matched]}")

        print("\nSample Follower Trades (first 5 and last 5):")
        for f in follower_details[:5]:
            print(f"  Follower {f['follower']} | ID: {f['history_id']} | Qty: {f['qty']} | Exit Time: {f['executed_at']} | Exit Price: {f['exit_price']}")
        print("  ...")
        for f in follower_details[-5:]:
            print(f"  Follower {f['follower']} | ID: {f['history_id']} | Qty: {f['qty']} | Exit Time: {f['executed_at']} | Exit Price: {f['exit_price']}")

    # Save full breakdown to json for reference
    with open("scratch/btc07_follower_audit.json", "w") as f:
        json.dump({
            "master_trades": m_matched,
            "follower_trades": follower_details
        }, f, indent=2)

if __name__ == "__main__":
    main()
