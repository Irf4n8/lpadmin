from playwright.sync_api import sync_playwright
import os

def capture_needed_screenshots():
    screenshot_dir = "mam_test_execution_reports/screenshots"
    os.makedirs(screenshot_dir, exist_ok=True)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1600, 'height': 900})
        page = context.new_page()
        
        print("Logging in as mammaster...")
        page.goto("https://lpadmin.blackfx.com/login", wait_until="networkidle", timeout=30000)
        page.fill('input[type="email"]', 'mammaster@mailinator.com')
        page.fill('input[type="password"]', 'Test@1234')
        page.click('button[type="submit"]')
        page.wait_for_timeout(3000)
        
        # Navigate to dashboard
        page.goto("https://lpadmin.blackfx.com/dashboard", wait_until="networkidle", timeout=35000)
        page.wait_for_timeout(3000)
        
        p1 = os.path.join(screenshot_dir, "MAM_Master_Dashboard_Active.png")
        page.screenshot(path=p1)
        print("Saved:", p1)
        
        browser.close()

if __name__ == "__main__":
    capture_needed_screenshots()
