from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    page.goto("https://lpadmin.blackfx.com/blackadmin", wait_until="networkidle")
    page.fill('input[type="email"], input[name="email"]', "lpadmin@blacktrader.com")
    page.fill('input[type="password"], input[name="password"]', "Raj1234!")
    page.click('button[type="submit"]')
    page.wait_for_timeout(3000)
    page.locator('text=MEMBERS').first.click()
    page.wait_for_timeout(3000)
    page.locator('input[placeholder*="email, name or user id"]').first.fill("mamf1@mailinator.com")
    page.wait_for_timeout(1500)
    
    # Let's inspect the entire row and its event listeners in JavaScript
    info = page.evaluate("""() => {
        const row = document.querySelector('tbody tr');
        if (!row) return 'No row';
        const td0 = row.querySelectorAll('td')[0];
        const td6 = row.querySelectorAll('td')[6];
        
        return {
            rowClick: !!row.onclick,
            td0HTML: td0.outerHTML,
            td6HTML: td6 ? td6.outerHTML : 'none',
            allTds: Array.from(row.querySelectorAll('td')).map((td, i) => `${i}: ${td.innerText.replace(/\\n/g, ' ')}`)
        };
    }""")
    print("Row info:", info)
    
    # Let's check what happens if we click td0
    print("\nClicking td0...")
    row_td0 = page.locator('tbody tr td').first
    row_td0.click()
    page.wait_for_timeout(2000)
    print("Current URL:", page.url)
    
    # Let's check if there are any new elements on the page (like a side drawer or detail view)
    page.screenshot(path="reports/screenshots/blackadmin/click_td0.png")
    
    # Let's check if there is an open drawer or side panel
    side_panel = page.evaluate("""() => {
        const aside = document.querySelector('aside, [class*=\"drawer\"], [class*=\"sheet\"], [class*=\"slide\"]');
        return aside ? aside.innerText : 'None';
    }""")
    print("Side panel text:", side_panel[:300])

    browser.close()
