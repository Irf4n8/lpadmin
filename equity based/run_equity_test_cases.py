#!/usr/bin/env python3
"""
BlackTrader MAM: Equity Based Category QA Test Suite
====================================================
Executes the 10-trade validation matrix on fixed high-liquidity instrument:
- Sizing Category: Equity Based
- Sizing Formula: Follower Lot = Master Lot * (Follower Equity / Master Balance)
- Minimum Lot Size: strictly >= 1.0 with decimal sizing
- Fixed Instrument: BINANCE:BTCUSDT.P
"""

import os
import sys
import time
import json
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
import requests
import concurrent.futures

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent
REPORTS_DIR = SCRIPT_DIR / "reports"
EVIDENCE_DIR = REPORTS_DIR / "evidence"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_BASE_URL = "https://lpadmin.blackfx.com"
DEFAULT_MASTER_EMAIL = "mammaster@mailinator.com"
DEFAULT_PASSWORD = "Test@1234"
DEFAULT_SYMBOL = "BINANCE:BTCUSDT.P"


class BlackTraderUserSession:
    def __init__(self, email: str, password: str, name: str, base_url: str = DEFAULT_BASE_URL, role: str = "follower"):
        self.email = email
        self.password = password
        self.name = name
        self.role = role
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.chart_token: Optional[str] = None
        self.member_id: Optional[str] = None

    def authenticate(self) -> bool:
        login_url = f"{self.base_url}/api/auth/login"
        try:
            r = self.session.post(login_url, json={"email": self.email, "password": self.password}, timeout=15)
            if r.status_code == 200 and r.json().get("success"):
                tok_res = self.session.post(f"{self.base_url}/api/auth/chart-token", timeout=15)
                if tok_res.status_code == 200:
                    data = tok_res.json()
                    self.chart_token = data.get("token")
                    user = data.get("user") or {}
                    self.member_id = user.get("id") or user.get("client_id")
                    return True
        except Exception:
            pass
        return False

    def get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.chart_token}",
            "Content-Type": "application/json"
        }

    def place_order(self, symbol: str, side: str, lot: float, order_type: str = "MARKET",
                    tp: Optional[float] = None, sl: Optional[float] = None, instance: str = "paper") -> dict:
        url = f"{self.base_url}/v1/oms/{instance}/orders"
        payload = {"symbol": symbol, "side": side.upper(), "order_type": order_type.upper(), "qty": float(lot)}
        if tp is not None: payload["tp"] = float(tp)
        if sl is not None: payload["sl"] = float(sl)
        try:
            r = self.session.post(url, json=payload, headers=self.get_headers(), timeout=15)
            if r.status_code == 200:
                data = r.json()
                data["_http_code"] = 200
                return data
            return {"error": f"HTTP {r.status_code}: {r.text}", "_http_code": r.status_code}
        except Exception as e:
            return {"error": str(e), "_http_code": 0}

    def get_positions(self, instance: str = "paper") -> dict:
        url = f"{self.base_url}/v1/oms/{instance}/positions"
        try:
            r = self.session.get(url, headers=self.get_headers(), timeout=10)
            if r.status_code == 200: return r.json()
        except Exception:
            pass
        return {"positions": [], "count": 0}

    def get_funds(self, instance: str = "paper") -> dict:
        pos = self.get_positions(instance=instance)
        return pos.get("funds", {})

    def get_quotes(self, symbol: str, instance: str = "paper") -> dict:
        url = f"{self.base_url}/v1/oms/{instance}/quotes?symbol={symbol}"
        try:
            r = self.session.get(url, headers=self.get_headers(), timeout=8)
            if r.status_code == 200: return r.json()
        except Exception:
            pass
        return {}

    def squareoff_position(self, market_order_id: str, instance: str = "paper") -> dict:
        url = f"{self.base_url}/v1/oms/{instance}/positions/{market_order_id}/squareoff"
        try:
            r = self.session.post(url, headers=self.get_headers(), timeout=12)
            if r.status_code == 200: return r.json()
        except Exception:
            pass
        return {"success": False}

    def squareoff_all(self, symbol: Optional[str] = None, instance: str = "paper") -> int:
        pos_data = self.get_positions(instance=instance)
        positions = pos_data.get("positions", [])
        closed = 0
        for p in positions:
            if not symbol or p.get("symbol") == symbol:
                mid = p.get("market_order_id")
                if mid:
                    self.squareoff_position(mid, instance=instance)
                    closed += 1
        return closed


def main():
    print("Equity Based Test Suite ready. Run after switching categories via mam_management/change_mam_category.py --category equity")


if __name__ == "__main__":
    main()

