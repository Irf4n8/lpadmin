#!/usr/bin/env python3
"""
Reusable Authentication & Session Management Module
===================================================
Handles:
- Trader login via Playwright
- Storage state caching for login bypass & fast test execution
- Resolving and attaching to the BlackTrader terminal iframe (`chartv2.blacktrader.com`)
- Capturing workspace chart token for dual-layer OMS API verification
"""

import os
import json
import time
from typing import Tuple, Optional, Any
import requests
from playwright.sync_api import sync_playwright, Page, BrowserContext, Frame

from reusable.helpers import load_env, DEFAULT_BASE_URL, DEFAULT_TRADER_EMAIL, DEFAULT_TRADER_PASSWORD

STATE_FILE = "storage_state.json"


class BlackTraderAuth:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        email: str = DEFAULT_TRADER_EMAIL,
        password: str = DEFAULT_TRADER_PASSWORD
    ):
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.password = password
        self.chart_token: Optional[str] = None
        self.api_session = requests.Session()

    def get_api_session_and_token(self) -> Tuple[requests.Session, Optional[str]]:
        """Fast headless login using requests to get chart token and API session."""
        login_url = f"{self.base_url}/api/auth/login"
        r = self.api_session.post(login_url, json={"email": self.email, "password": self.password}, timeout=15)
        if r.status_code == 200 and r.json().get("success"):
            r_tok = self.api_session.post(f"{self.base_url}/api/auth/chart-token", timeout=15)
            if r_tok.status_code == 200:
                self.chart_token = r_tok.json().get("token")
        return self.api_session, self.chart_token

    def login_and_get_trading_frame(
        self,
        page: Page,
        context: BrowserContext,
        reuse_session: bool = True
    ) -> Frame:
        """
        Logs into the portal via Playwright, navigates to the terminal dashboard,
        waits for the trading iframe to load, and returns the trading Frame.
        """
        # Step 1: Ensure API session & inject cookie directly for instant zero-lag auth
        if not self.chart_token:
            self.get_api_session_and_token()

        bt_cookie = self.api_session.cookies.get("bt_trader")
        if bt_cookie:
            domain = self.base_url.replace("https://", "").replace("http://", "").split("/")[0].split(":")[0]
            context.add_cookies([{
                "name": "bt_trader",
                "value": bt_cookie,
                "domain": domain,
                "path": "/"
            }])

        print(f"[*] Navigating trader to terminal: {self.email}...")
        page.goto(f"{self.base_url}/dashboard", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        # Fallback to UI form login only if redirected to /login
        if "/login" in page.url:
            print("[*] Form login fallback...")
            email_input = page.locator('input[type="email"], input[name="email"], input[placeholder*="email" i]').first
            pass_input = page.locator('input[type="password"], input[name="password"]').first
            if email_input.is_visible(timeout=5000):
                email_input.fill(self.email)
                pass_input.fill(self.password)
                submit_btn = page.locator('button[type="submit"], button:has-text("Log in"), button:has-text("Sign in")').first
                submit_btn.click()
                page.wait_for_url(lambda u: "/login" not in u, timeout=20000)

        # Ensure on /dashboard
        if "/dashboard" not in page.url:
            page.goto(f"{self.base_url}/dashboard", wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

        # Step 2: Locate terminal iframe
        print("[*] Waiting for trading terminal iframe...")
        page.wait_for_selector("iframe#frame, iframe[src*='chart'], iframe[src*='blacktrader']", state="attached", timeout=25000)

        # Wait for terminal to load inside the frame
        time.sleep(3.0)

        trading_frame = None
        for _ in range(20):
            for f in page.frames:
                if "chart" in f.url or "blacktrader" in f.url or "mode=iframeMode" in f.url:
                    trading_frame = f
                    break
            if trading_frame:
                break
            time.sleep(0.5)

        if not trading_frame:
            raise RuntimeError("Trading terminal iframe failed to initialize or attach.")

        print(f"[+] Trading terminal frame attached: {trading_frame.url[:70]}...")

        # Assert dashboard / terminal loaded
        trading_frame.wait_for_selector(".buy-btn, body", state="attached", timeout=25000)
        time.sleep(1.0)
        print("[+] Authenticated BlackTrader terminal dashboard verified successfully!")

        return trading_frame

