from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    
    requests_log = []
    responses_log = []
    
    def on_req(req):
        requests_log.append((req.method, req.url, req.post_data))
        
    def on_res(res):
        responses_log.append((res.status, res.url))
        
    page.on("request", on_req)
    page.on("response", on_res)
    
    page.goto("https://lpadmin.blackfx.com/login", wait_until="networkidle")
    page.fill('input[type="email"]', 'mamm@mailinator.com')
    page.fill('input[type="password"]', '12345678')
    page.click('button[type="submit"]')
    page.wait_for_timeout(4000)
    
    print("=== NETWORK CALLS DURING WEB LOGIN ===")
    for m, u, d in requests_log:
        if any(k in u for k in ["login", "auth", "token", "chart", "oms"]):
            print(f"{m:6} {u}")
            if d:
                print(f"       POST Data: {d[:100]}")
                
    browser.close()
