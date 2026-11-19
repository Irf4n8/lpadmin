from playwright.sync_api import sync_playwright
import time
import os
import requests

SCREENSHOT_DIR = os.path.abspath("reports/screenshots/negative_balance")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

BASE_URL = "https://lpadmin.blackfx.com"

# 1. Capture BlackAdmin UI showing Negative Balance
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    
    print("[1] Capturing BlackAdmin UI with Negative Balance...")
    page.goto(f"{BASE_URL}/blackadmin", wait_until="networkidle")
    page.fill('input[type="email"], input[name="email"]', "lpadmin@blacktrader.com")
    page.fill('input[type="password"], input[name="password"]', "Raj1234!")
    page.click('button[type="submit"]')
    page.wait_for_timeout(3000)
    
    page.locator('text=MEMBERS').first.click()
    page.wait_for_timeout(3000)
    page.locator('input[placeholder*="email, name or user id"]').first.fill("mamf1@mailinator.com")
    page.wait_for_timeout(1500)
    
    row_td0 = page.locator('tbody tr td').first
    row_td0.click()
    page.wait_for_timeout(2500)
    
    admin_neg_path = os.path.join(SCREENSHOT_DIR, "01_blackadmin_negative_balance_mamf1.png")
    page.screenshot(path=admin_neg_path)
    print("Saved:", admin_neg_path)
    
    # 2. Login to Trader terminal as mamf1 to capture negative balance in trader UI
    print("\n[2] Capturing BlackTrader Trader Portal with Negative Balance...")
    page2 = browser.new_page(viewport={"width": 1600, "height": 1000})
    page2.goto(f"{BASE_URL}/login", wait_until="networkidle")
    page2.fill('input[type="email"], input[name="email"]', "mamf1@mailinator.com")
    page2.fill('input[type="password"], input[name="password"]', "12345678")
    page2.click('button[type="submit"]')
    page2.wait_for_timeout(3000)
    
    account_path = os.path.join(SCREENSHOT_DIR, "02_mamf1_account_portal.png")
    page2.screenshot(path=account_path)
    print("Saved:", account_path)
    
    # Open terminal
    page2.goto(f"{BASE_URL}/dashboard", wait_until="networkidle")
    page2.wait_for_timeout(7000)
    
    terminal_path = os.path.join(SCREENSHOT_DIR, "03_mamf1_terminal_negative_balance.png")
    page2.screenshot(path=terminal_path)
    print("Saved:", terminal_path)
    
    browser.close()

# 3. Test API vulnerabilities on this negative balance
print("\n[3] Testing vulnerabilities while mamf1 balance is negative...")
s = requests.Session()
r_login = s.post(f"{BASE_URL}/api/auth/login", json={"email": "mamf1@mailinator.com", "password": "12345678"})
t_tok = s.post(f"{BASE_URL}/api/auth/chart-token").json().get("token")
headers = {"Authorization": f"Bearer {t_tok}", "Content-Type": "application/json"}

# Bug A: Can pending limit order be placed while negative?
r_pending = s.post(f"{BASE_URL}/v1/oms/real/orders/pending", json={
    "symbol": "BINANCE:BTCUSDT.P",
    "side": "buy",
    "quantity": 0.001,
    "price": 60000.0,
    "type": "limit"
}, headers=headers)
print("Pending limit order while negative balance response:", r_pending.status_code, r_pending.text)

# Bug B: Can withdrawal OTP be generated while negative?
r_otp = s.post(f"{BASE_URL}/portal/withdrawals/otp", headers={"Authorization": f"Bearer {r_login.json().get('token')}"})
print("Withdrawal OTP generation while negative balance response:", r_otp.status_code, r_otp.text)

# Bug C: Can internal wallet transfer be initiated?
r_wal = s.post(f"{BASE_URL}/wallets/transfer", json={
    "from_wallet_id": "trading_real",
    "to_wallet_id": "client_wallet",
    "amount": 50.0
}, headers={"Authorization": f"Bearer {r_login.json().get('token')}"})
print("Internal transfer while negative balance response:", r_wal.status_code, r_wal.text)
