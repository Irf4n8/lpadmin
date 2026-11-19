from playwright.sync_api import sync_playwright
import json

def get_mam_docs():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        mam_endpoints = [
            "mamListMasters",
            "mamBecomeMaster",
            "mamListFollows",
            "mamFollow",
            "mamUnfollow",
            "mamListShares",
            "copyFollow",
            "placeMarketOrder",
            "placePendingOrder",
            "modifyOrder",
            "cancelOrder",
            "setPositionProtection",
            "squareOffPosition",
            "reducePosition",
            "bulkSquareOffPositions",
            "getFunds"
        ]
        
        results = {}
        for ep in mam_endpoints:
            page.goto(f"https://lpadmin.blackfx.com/api#docs/{ep}", wait_until="networkidle")
            page.wait_for_timeout(1000)
            
            content = page.evaluate("""() => {
                const el = document.querySelector('#developer-content') || document.body;
                return el.innerText;
            }""")
            results[ep] = content
            
        with open("scratch/key_api_docs.json", "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
            
        print("Scraped", len(results), "endpoints successfully.")
        browser.close()

if __name__ == "__main__":
    get_mam_docs()

