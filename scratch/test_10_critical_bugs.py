import sys, os, time, math, concurrent.futures
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from test_suite.client import BlackTraderClient

def run_bug_experiments():
    client = BlackTraderClient()
    base_url = "https://lpadmin.blackfx.com"
    instance = "real"
    
    admin_tok = client.get_admin_token()
    master_tok = client.get_trader_token("mammaster@mailinator.com", "Test@1234")
    f1_tok = client.get_trader_token("mamfollower1@mailinator.com", "Test@1234")
    
    m_headers = {"Authorization": f"Bearer {master_tok}"}
    f1_headers = {"Authorization": f"Bearer {f1_tok}"}
    a_headers = {"Authorization": f"Bearer {admin_tok}"}
    
    print("[1] Testing BUG-01: Inverted / Crossed Bracket Order Entry...")
    # Attempt to place pending order with inverted SL/TP
    # Market price ~64,500. Buy Limit at 60,000, but SL at 62,000 (higher than entry)
    crossed_payload = {
        "symbol": "BINANCE:BTCUSDT.P",
        "side": "BUY",
        "type": "LIMIT",
        "price": 60000.0,
        "quantity": 0.001,
        "stop_loss": 62000.0, # INVALID: SL higher than Buy price!
        "take_profit": 58000.0 # INVALID: TP lower than Buy price!
    }
    r1 = client.request_with_retry("POST", f"{base_url}/v1/oms/{instance}/orders/pending", headers=m_headers, json=crossed_payload)
    print("BUG-01 Response:", r1.status_code, r1.text[:200])
    if r1.status_code in [200, 201]:
        ord_id = r1.json().get("order", {}).get("order_id")
        print("  -> BUG CONFIRMED: Backend OMS accepted inverted SL/TP order without server-side validation!")
        if ord_id:
            client.request_with_retry("DELETE", f"{base_url}/v1/oms/{instance}/orders/{ord_id}", headers=m_headers)

    print("\n[2] Testing BUG-02: Mid-Trade Unfollow Orphan Child Position...")
    # Master opens trade
    r_open = client.request_with_retry("POST", f"{base_url}/v1/oms/{instance}/orders", headers=m_headers, json={"symbol": "BINANCE:BTCUSDT.P", "side": "BUY", "type": "MARKET", "quantity": 0.001})
    m_order = r_open.json().get("order", {})
    mid = m_order.get("market_order_id")
    print("Master opened trade:", mid)
    time.sleep(2)
    
    # Check follower1 has position
    r_f1_pos = client.request_with_retry("GET", f"{base_url}/v1/oms/{instance}/positions", headers=f1_headers)
    f1_positions = r_f1_pos.json().get("positions", [])
    print("Follower1 positions count before unfollow:", len(f1_positions))
    
    # Follower1 unfollows
    rf = client.request_with_retry("GET", f"{base_url}/v1/oms/{instance}/mam/follows", headers=m_headers)
    master_cid = rf.json().get("master", {}).get("client_id")
    r_unf = client.request_with_retry("POST", f"{base_url}/v1/oms/{instance}/mam/unfollow", headers=f1_headers, json={"master_client_id": master_cid})
    print("Follower1 unfollow response:", r_unf.status_code, r_unf.text[:100])
    
    # Master closes trade
    if mid:
        r_close = client.request_with_retry("POST", f"{base_url}/v1/oms/{instance}/positions/{mid}/squareoff", headers=m_headers)
        print("Master closed trade:", r_close.status_code)
    time.sleep(2)
    
    # Check if follower1 still has orphan position!
    r_f1_pos_after = client.request_with_retry("GET", f"{base_url}/v1/oms/{instance}/positions", headers=f1_headers)
    f1_pos_after = r_f1_pos_after.json().get("positions", [])
    print("Follower1 positions count after master squareoff:", len(f1_pos_after))
    if len(f1_pos_after) > 0:
        print("  -> BUG CONFIRMED: Follower position orphaned! Unfollowing detached listener while leaving live trade open.")
        for p in f1_pos_after:
            fmid = p.get("market_order_id")
            if fmid:
                client.request_with_retry("POST", f"{base_url}/v1/oms/{instance}/positions/{fmid}/squareoff", headers=f1_headers)
                
    # Re-follow master
    client.request_with_retry("POST", f"{base_url}/v1/oms/{instance}/mam/follow", headers=f1_headers, json={"master_client_id": master_cid, "multiplier": 2.0})

    print("\n[3] Testing BUG-03: Zero/Negative Balance Order Placement & Allocation...")
    # Check what happens if a follower balance is set to 0.00
    members = client.get_admin_members()
    f2 = next(m for m in members if m.get("email") == "mamfollower2@mailinator.com")
    f2_id = f2.get("member_id")
    orig_bal = f2.get("balances", {}).get("real", 10000000)
    
    # Set to 0
    client.set_member_balance(f2_id, 0.0, instance=instance)
    f2_tok = client.get_trader_token("mamfollower2@mailinator.com", "Test@1234")
    f2_headers = {"Authorization": f"Bearer {f2_tok}"}
    r_f2_funds = client.request_with_retry("GET", f"{base_url}/v1/oms/{instance}/funds", headers=f2_headers)
    print("Follower2 funds with 0 balance:", r_f2_funds.json().get("funds", {}))
    
    # Master places trade
    r_m_trade = client.request_with_retry("POST", f"{base_url}/v1/oms/{instance}/orders", headers=m_headers, json={"symbol": "BINANCE:BTCUSDT.P", "side": "BUY", "type": "MARKET", "quantity": 0.001})
    m_mid = r_m_trade.json().get("order", {}).get("market_order_id")
    time.sleep(2)
    
    # Check if follower2 attempted to fill with zero margin or failed
    r_f2_orders = client.request_with_retry("GET", f"{base_url}/v1/oms/{instance}/orders", headers=f2_headers)
    latest_f2_order = r_f2_orders.json().get("orders", [])[0] if r_f2_orders.json().get("orders") else {}
    print("Follower2 latest order with 0 balance:", latest_f2_order.get("state"), latest_f2_order.get("requested_qty"))
    
    if m_mid:
        client.request_with_retry("POST", f"{base_url}/v1/oms/{instance}/positions/{m_mid}/squareoff", headers=m_headers)
    # Restore balance
    client.set_member_balance(f2_id, orig_bal, instance=instance)

    print("\n[4] Testing BUG-04: Simultaneous Double Square-Off Race Condition...")
    r_open = client.request_with_retry("POST", f"{base_url}/v1/oms/{instance}/orders", headers=m_headers, json={"symbol": "BINANCE:BTCUSDT.P", "side": "BUY", "type": "MARKET", "quantity": 0.001})
    mid4 = r_open.json().get("order", {}).get("market_order_id")
    time.sleep(1)
    
    # Fire simultaneous squareoff requests
    def fire_sq():
        return client.request_with_retry("POST", f"{base_url}/v1/oms/{instance}/positions/{mid4}/squareoff", headers=m_headers)
        
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        futs = [ex.submit(fire_sq), ex.submit(fire_sq)]
        responses = [f.result() for f in futs]
        
    print("Simultaneous squareoff status codes:", [r.status_code for r in responses])
    print("Responses:", [r.text[:80] for r in responses])

    print("\n[5] Testing BUG-05: Sub-0.001 Fractional Multiplier Underflow (0.001 lot * 0.1 multiplier)...")
    # Master sends 0.001 lots
    # Follower with 0.1 multiplier = 0.0001 lots (below Binance 0.001 min step)
    r_fol = client.request_with_retry("POST", f"{base_url}/v1/oms/{instance}/mam/follow", headers=f1_headers, json={"master_client_id": master_cid, "multiplier": 0.1})
    print("Follow with 0.1 multiplier:", r_fol.status_code)
    
    r_open5 = client.request_with_retry("POST", f"{base_url}/v1/oms/{instance}/orders", headers=m_headers, json={"symbol": "BINANCE:BTCUSDT.P", "side": "BUY", "type": "MARKET", "quantity": 0.001})
    mid5 = r_open5.json().get("order", {}).get("market_order_id")
    time.sleep(2)
    
    r_f1_ord = client.request_with_retry("GET", f"{base_url}/v1/oms/{instance}/orders", headers=f1_headers)
    last_f1_ord = r_f1_ord.json().get("orders", [])[0] if r_f1_ord.json().get("orders") else {}
    print("Follower1 order under sub-lot underflow:", last_f1_ord.get("order_id"), last_f1_ord.get("state"), "qty:", last_f1_ord.get("requested_qty"))
    
    if mid5:
        client.request_with_retry("POST", f"{base_url}/v1/oms/{instance}/positions/{mid5}/squareoff", headers=m_headers)
    # Restore multiplier
    client.request_with_retry("POST", f"{base_url}/v1/oms/{instance}/mam/follow", headers=f1_headers, json={"master_client_id": master_cid, "multiplier": 2.0})

if __name__ == "__main__":
    run_bug_experiments()

