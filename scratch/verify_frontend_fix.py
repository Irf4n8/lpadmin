import os
from playwright.sync_api import sync_playwright

def main():
    os.makedirs("reports", exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 900})
        page.goto("http://localhost:8500", wait_until="networkidle")

        js_code = """
        () => {
            autoSyncActive = false;
            if (syncInterval) clearInterval(syncInterval);
            currentData.master_positions = [{
                account: 'mammaster@mailinator.com',
                market_order_id: 'ord_de9630fddb48f1a451',
                symbol: 'BINANCE:BTCUSDT.P',
                side: 'BUY',
                type: 'MARKET',
                qty: 0.001,
                net_qty: 0.001,
                avg_entry_price: 64954.50,
                current_price: 64989.80,
                unrealized_pnl: 0.04
            }];
            currentData.follower_positions = [
                {
                    account: 'mamfollower1@mailinator.com',
                    market_order_id: 'ord_aa0476b4e833e5bd19',
                    symbol: 'BINANCE:BTCUSDT.P',
                    side: 'BUY',
                    type: 'MARKET',
                    category: 'multiplier',
                    multiplier: 0.25,
                    qty: 0.001,
                    net_qty: 0.001,
                    master_qty: 0.001,
                    avg_entry_price: 64954.50,
                    current_price: 64989.80,
                    unrealized_pnl: 0.04
                },
                {
                    account: 'mamfollower2@mailinator.com',
                    market_order_id: 'ord_75764b0e84ada0bb95',
                    symbol: 'BINANCE:BTCUSDT.P',
                    side: 'BUY',
                    type: 'MARKET',
                    category: 'multiplier',
                    multiplier: 0.25,
                    qty: 0.001,
                    net_qty: 0.001,
                    master_qty: 0.001,
                    avg_entry_price: 64954.50,
                    current_price: 64989.80,
                    unrealized_pnl: 0.04
                },
                {
                    account: 'mamfollower3@mailinator.com',
                    market_order_id: 'ord_8c30a0476b4e833e5b',
                    symbol: 'BINANCE:BTCUSDT.P',
                    side: 'BUY',
                    type: 'MARKET',
                    category: 'multiplier',
                    multiplier: 0.25,
                    qty: 0.001,
                    net_qty: 0.001,
                    master_qty: 0.001,
                    avg_entry_price: 64954.50,
                    current_price: 64989.80,
                    unrealized_pnl: 0.04
                },
                {
                    account: 'mamfollower4@mailinator.com',
                    market_order_id: 'ord_9d40a0476b4e833e5c',
                    symbol: 'BINANCE:BTCUSDT.P',
                    side: 'BUY',
                    type: 'MARKET',
                    category: 'multiplier',
                    multiplier: 0.25,
                    qty: 0.001,
                    net_qty: 0.001,
                    master_qty: 0.001,
                    avg_entry_price: 64954.50,
                    current_price: 64989.80,
                    unrealized_pnl: 0.04
                },
                {
                    account: 'mamfollower5@mailinator.com',
                    market_order_id: 'ord_0e50a0476b4e833e5d',
                    symbol: 'BINANCE:BTCUSDT.P',
                    side: 'BUY',
                    type: 'MARKET',
                    category: 'multiplier',
                    multiplier: 0.25,
                    qty: 0.001,
                    net_qty: 0.001,
                    master_qty: 0.001,
                    avg_entry_price: 64954.50,
                    current_price: 64989.80,
                    unrealized_pnl: 0.04
                }
            ];
            renderMasterPositions();
            renderFollowerPositions();
            const tabBtn = document.querySelectorAll('.tab-item')[1];
            switchTab('follower-pos', tabBtn);
        }
        """
        page.evaluate(js_code)
        page.wait_for_timeout(1000)

        # Check DOM rows
        rows = page.evaluate("""
        () => {
            return Array.from(document.querySelectorAll('#followerPositionsBody tr')).map(r => {
                const tds = Array.from(r.querySelectorAll('td'));
                return {
                    account: tds[0]?.innerText.trim(),
                    category: tds[3]?.innerText.trim(),
                    follower_qty: tds[7]?.innerText.trim(),
                    master_qty: tds[8]?.innerText.trim(),
                    multiplier: tds[9]?.innerText.trim()
                };
            });
        }
        """)
        print("Follower Positions verification:")
        for r in rows:
            print(r)

        dest = "reports/verified_follower_positions_fixed.png"
        page.screenshot(path=dest)
        print("Screenshot saved to", dest)
        browser.close()

if __name__ == "__main__":
    main()
