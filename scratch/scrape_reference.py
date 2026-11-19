from playwright.sync_api import sync_playwright
import json

def get_all_reference_endpoints():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://lpadmin.blackfx.com/api#docs/reference", wait_until="networkidle")
        page.wait_for_timeout(3000)
        
        # Extract endpoints info from DOM
        data = page.evaluate("""() => {
            const endpoints = [];
            // look for endpoint cards or lists
            const sections = document.querySelectorAll('section, [data-endpoint], .endpoint, .doc-endpoint, tr');
            
            // Also let's extract all text from main content
            const main = document.querySelector('#developer-content') || document.querySelector('main') || document.body;
            
            const links = Array.from(document.querySelectorAll('a[href^="#docs/"]')).map(a => ({
                text: a.innerText.replace(/\\s+/g, ' ').trim(),
                href: a.getAttribute('href')
            }));
            
            return {
                text: main.innerText,
                links: links
            };
        }""")
        
        with open("scratch/api_reference_dump.txt", "w", encoding="utf-8") as f:
            f.write(data["text"])
            
        with open("scratch/api_reference_links.json", "w", encoding="utf-8") as f:
            json.dump(data["links"], f, indent=2)
            
        print("Total links matching #docs/:", len(data["links"]))
        print("Main text length:", len(data["text"]))
        print("First 2000 chars:")
        print(data["text"][:2000])
        
        browser.close()

if __name__ == "__main__":
    get_all_reference_endpoints()

