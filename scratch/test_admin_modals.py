from playwright.sync_api import sync_playwright
import time
import os

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
    
    row = page.locator('tbody tr:has-text("mamf1@mailinator.com")').first
    
    # 1. Click Actions menu (Btn 2)
    print("\n--- Testing Actions Menu ---")
    action_btn = row.locator('button[title*="Actions for"]').first
    action_btn.click()
    page.wait_for_timeout(1000)
    
    # Check open menu items
    menu_items = page.locator('[role="menu"] [role="menuitem"], .menu-item, [class*="menu"] button, [class*="dropdown"] button, [class*="popover"] button').all()
    print("Menu items count:", len(menu_items))
    for m in menu_items:
        print("  Menu item:", m.inner_text().strip())
    page.screenshot(path="reports/screenshots/blackadmin/10_actions_menu.png")
    
    # Press Escape to close menu
    page.keyboard.press("Escape")
    page.wait_for_timeout(1000)
    
    # 2. Click the balance button (Btn 0)
    print("\n--- Testing Balance Button Click ---")
    bal_btn = row.locator('button:has-text("paper")').first
    bal_btn.click()
    page.wait_for_timeout(1500)
    
    page.screenshot(path="reports/screenshots/blackadmin/11_balance_button_clicked.png")
    
    # Check if a dialog/modal/prompt opened
    prompts = page.locator('dialog, [role="dialog"], .modal, [class*="modal"], [class*="dialog"], [class*="popover"]').all()
    print("Modals/Dialogs found:", len(prompts))
    for p_el in prompts:
        print("Dialog text preview:", p_el.inner_text().replace('\n', ' | ')[:300])
        
    inputs = page.locator('dialog input, [role="dialog"] input, [class*="modal"] input, [class*="dialog"] input').all()
    print("Modal inputs:", len(inputs))
    for inp in inputs:
        print("  Input:", inp.get_attribute("placeholder"), inp.get_attribute("type"), inp.get_attribute("value"))
        
    btns = page.locator('dialog button, [role="dialog"] button, [class*="modal"] button, [class*="dialog"] button').all()
    print("Modal buttons:", len(btns))
    for b in btns:
        print("  Button:", b.inner_text().strip())
        
    browser.close()
