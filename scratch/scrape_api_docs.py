from playwright.sync_api import sync_playwright

def inspect_docs():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://lpadmin.blackfx.com/api#docs/overview", wait_until="networkidle")
        page.wait_for_timeout(3000)
        
        title = page.title()
        print("Page Title:", title)
        
        # Check nav items or doc headings
        text = page.inner_text("body")
        print("Body text length:", len(text))
        print("First 1000 characters of doc:")
        print(text[:1000])
        
        with open("scratch/developer_api_docs_dump.txt", "w", encoding="utf-8") as f:
            f.write(text)
            
        browser.close()

if __name__ == "__main__":
    inspect_docs()

