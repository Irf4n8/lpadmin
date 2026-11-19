from playwright.sync_api import sync_playwright
import json

def get_mam_docs():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        mam_endpoints = [
            "mamMasters",
            "mamMaster",
            "mamFollows",
            "mamFollow",
            "mamUnfollow",
            "mamShares"
        ]
        
        results = {}
        for ep in mam_endpoints:
            page.goto(f"https://lpadmin.blackfx.com/api#docs/{ep}", wait_until="networkidle")
            page.wait_for_timeout(1000)
            
            # Extract content from doc-view or main
            content = page.evaluate("""() => {
                const el = document.querySelector('.doc-endpoint') || document.querySelector('#developer-content') || document.body;
                return el.innerText;
            }""")
            results[ep] = content
            print(f"=== {ep} ===")
            print(content[:500])
            print("\n")
            
        with open("scratch/mam_docs_details.json", "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
            
        browser.close()

if __name__ == "__main__":
    get_mam_docs()

