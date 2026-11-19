from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    page.goto("https://lpadmin.blackfx.com/blackadmin", wait_until="networkidle")
    page.fill('input[type="email"]', "lpadmin@blacktrader.com")
    page.fill('input[type="password"]', "Raj1234!")
    page.click('button[type="submit"]')
    time.sleep(3)
    page.locator('text=Members').first.click()
    time.sleep(2)
    inp = page.locator('input[placeholder*="email, name or user id"]').first
    inp.fill("mamf1@mailinator.com")
    time.sleep(3)
    
    # Check elements in table or list
    rows = page.locator('table tr, [role="row"]').all()
    print("Found rows:", len(rows))
    for i, r in enumerate(rows[:5]):
        print(f"Row {i}:", r.inner_text().replace('\n', ' | '))
        
    # Also find all clickable items in table area
    cells = page.locator('tbody td, [role="cell"], a').all()
    print("Clickable targets:")
    for c in cells[:15]:
        txt = c.inner_text().strip()
        if txt and 'mamf1' in txt.lower():
            print("Target:", txt)
            c.click()
            time.sleep(3)
            page.screenshot(path="reports/screenshots/blackadmin/06_clicked_target.png")
            print("Saved 06_clicked_target.png")
            break

    # Check modal/drawer
    drawer = page.locator('[role="dialog"], aside, .drawer, .modal')
    if drawer.count() > 0:
        print("Drawer text:\n", drawer.first.inner_text()[:600])

    browser.close()
