from playwright.sync_api import sync_playwright
import time
import os

def admin_set_balance(email: str, balance: float, account_type: str = "real", screenshot_name: str = "admin_balance_set.png"):
    SCREENSHOT_DIR = os.path.abspath("reports/screenshots/blackadmin")
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        
        print(f"[Admin UI] Logging in...")
        page.goto("https://lpadmin.blackfx.com/blackadmin", wait_until="networkidle")
        page.fill('input[type="email"], input[name="email"]', "lpadmin@blacktrader.com")
        page.fill('input[type="password"], input[name="password"]', "Raj1234!")
        page.click('button[type="submit"]')
        page.wait_for_timeout(3000)
        
        # 1. Admin -> Members
        print("[Admin UI] Navigating to MEMBERS...")
        page.locator('text=MEMBERS').first.click()
        page.wait_for_timeout(3000)
        
        # 2. Search member
        print(f"[Admin UI] Searching for {email}...")
        search_box = page.locator('input[placeholder*="email, name or user id"]').first
        search_box.fill(email)
        page.wait_for_timeout(1500)
        
        # 3. Click member to open drawer
        print(f"[Admin UI] Clicking member {email}...")
        row_td0 = page.locator(f'tbody tr:has-text("{email}") td').first
        row_td0.click()
        page.wait_for_timeout(2500)
        
        # 4. In Money card, locate the target row (Real or Paper)
        card_label = "Real (Hedging)" if account_type == "real" else "Paper (Hedging)"
        print(f"[Admin UI] Locating {card_label} row...")
        target_row = page.locator(f'.section-gap:has-text("{card_label}")').first
        
        # Click "Set balance"
        btn_set_bal = target_row.locator('button:has-text("Set balance")').first
        btn_set_bal.click()
        page.wait_for_timeout(1000)
        
        # Fill new balance into input
        bal_input = target_row.locator('input[type="number"]').first
        bal_input.fill(str(balance))
        page.wait_for_timeout(500)
        
        # Capture screenshot right before clicking 'Set'
        pre_shot = os.path.join(SCREENSHOT_DIR, f"pre_{screenshot_name}")
        page.screenshot(path=pre_shot)
        print(f"[Admin UI] Saved pre-submit screenshot: {pre_shot}")
        
        # Click 'Set'
        btn_confirm = target_row.locator('button:has-text("Set")').first
        btn_confirm.click()
        page.wait_for_timeout(3000)
        
        post_shot = os.path.join(SCREENSHOT_DIR, f"post_{screenshot_name}")
        page.screenshot(path=post_shot)
        print(f"[Admin UI] Saved post-submit screenshot: {post_shot}")
        
        # Check current balance displayed
        current_bal_text = target_row.locator('b').inner_text()
        print(f"[Admin UI] Balance successfully updated to: {current_bal_text}")
        
        browser.close()
        return current_bal_text

if __name__ == "__main__":
    admin_set_balance("mamf1@mailinator.com", 200.0, "real", "mamf1_200_balance.png")
