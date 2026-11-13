"""
High-Performance Concurrent API Client for BlackTrader / OMS
============================================================
Features:
- Thread-safe session pooling.
- Token caching per account.
- ThreadPoolExecutor with max 10 concurrent workers.
- Exponential backoff & retry on 429 / 5xx errors.
- Full helper methods for Orders, Positions, Protection (TP/SL), Squareoff, Reduce, and Copy-trading.
"""

import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Add root directory to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config.settings import (
    BASE_URL,
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    MEMBER_PASSWORD,
    DEFAULT_PREFIX,
    DEFAULT_DOMAIN,
)


PAPER_UNFOLLOW_REASON = ("platform rule (observed 2026-11-12): paper copy links can no longer be CREATED, only ended - "
                         "an unfollowed paper follower cannot be re-linked. Set BT_ALLOW_PAPER_UNFOLLOW=1 to override.")


def paper_unfollow_blocked(instance: str) -> bool:
    """True when unfollowing on this instance would permanently drop the follower (paper, no override).
    Used by the dashboard's copy-settings actions only; BlackTraderClient.unfollow_master itself is unchanged."""
    return instance in ("paper", "paper-net") and os.environ.get("BT_ALLOW_PAPER_UNFOLLOW") != "1"


class BlackTraderClient:
    def __init__(self, base_url: str = BASE_URL, max_workers: int = 10, timeout: int = 15):
        self.base_url = base_url.rstrip("/")
        self.max_workers = max_workers
        self.timeout = timeout
        self._lock = threading.Lock()
        self._tokens: Dict[str, str] = {}  # email -> chart_token
        self._admin_token: Optional[str] = None

        # Thread-safe persistent session with retries
        self.session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PUT", "DELETE"]
        )
        adapter = HTTPAdapter(max_retries=retries, pool_connections=max_workers * 2, pool_maxsize=max_workers * 2)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def request_with_retry(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        json: Optional[Any] = None,
        params: Optional[Dict[str, Any]] = None,
        max_attempts: int = 4
    ) -> requests.Response:
        """Execute request with exponential backoff on 429 and network errors."""
        headers = headers or {}
        attempt = 0
        while attempt < max_attempts:
            attempt += 1
            try:
                resp = self.session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=json,
                    params=params,
                    timeout=self.timeout
                )
                if resp.status_code == 429:
                    retry_after = float(resp.headers.get("Retry-After", 1.5 * (2 ** (attempt - 1))))
                    time.sleep(retry_after)
                    continue
                return resp
            except (requests.ConnectionError, requests.Timeout) as e:
                if attempt >= max_attempts:
                    raise e
                time.sleep(1.0 * (2 ** (attempt - 1)))
        return resp

    # -------------------------------------------------------------------------
    # Authentication & Tokens
    # -------------------------------------------------------------------------
    def get_admin_token(self) -> str:
        with self._lock:
            if self._admin_token:
                return self._admin_token
            resp = self.request_with_retry(
                "POST",
                f"{self.base_url}/admin/api/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "remember": True}
            )
            if resp.status_code != 200:
                raise RuntimeError(f"Admin login failed: HTTP {resp.status_code} - {resp.text}")
            self._admin_token = resp.json().get("token")
            return self._admin_token

    def get_admin_members(self) -> List[Dict[str, Any]]:
        """Fetch all members list from admin API."""
        token = self.get_admin_token()
        resp = self.request_with_retry("GET", f"{self.base_url}/admin/api/members", headers={"Authorization": f"Bearer {token}"})
        if resp.status_code == 200:
            return resp.json().get("members", [])
        return []

    def set_member_status(self, member_id: str, status: str = "active") -> Dict[str, Any]:
        """Update a member's status (active / disabled) via admin API."""
        token = self.get_admin_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        resp = self.request_with_retry("POST", f"{self.base_url}/admin/api/members/{member_id}/status", headers=headers, json={"status": status})
        return {"status_code": resp.status_code, "data": resp.json() if resp.status_code == 200 else resp.text}

    def get_member_books(self) -> Dict[str, Dict[str, Any]]:
        """email -> {member_id, book ('a' / 'b'), account_type, status} for every member (admin API)."""
        out: Dict[str, Dict[str, Any]] = {}
        for m in self.get_admin_members():
            out[m.get("email", "")] = {
                "member_id": m.get("member_id"),
                "book": (m.get("book") or "").lower(),
                "account_type": m.get("account_type"),
                "status": m.get("status"),
            }
        return out

    def set_member_book(self, member_id: str, book: str) -> Dict[str, Any]:
        """Switch one member to A-book ('a': real orders go to the liquidity provider) or B-book ('b': booked on the
        platform's own engine). Paper accounts are always booked internally, so this only changes REAL routing.
        Admin API: POST /admin/api/members/{member_id}/book  {"book": "a"|"b"}"""
        if book not in ("a", "b"):
            raise ValueError("book must be 'a' or 'b'")
        token = self.get_admin_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        resp = self.request_with_retry("POST", f"{self.base_url}/admin/api/members/{member_id}/book", headers=headers, json={"book": book})
        return {"status_code": resp.status_code, "data": resp.json() if resp.status_code == 200 else resp.text}

    def set_member_balance(self, member_id: str, balance: float, instance: str = "paper") -> Dict[str, Any]:
        """Update a member's balance via admin API."""
        token = self.get_admin_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {"instance": instance, "balance": balance, "remark": "Automated Test Adjustment", "force": True}
        resp = self.request_with_retry("POST", f"{self.base_url}/admin/api/members/{member_id}/balance", headers=headers, json=payload)
        return {"status_code": resp.status_code, "data": resp.json() if resp.status_code == 200 else resp.text}

    def get_trader_token(self, email: str, password: str = MEMBER_PASSWORD, force_refresh: bool = False) -> str:
        with self._lock:
            if not force_refresh and email in self._tokens:
                return self._tokens[email]

        # Use an isolated session to prevent cookie race conditions between concurrent threads
        auth_session = requests.Session()
        login_resp = auth_session.post(
            f"{self.base_url}/api/auth/login",
            json={"email": email, "password": password},
            timeout=self.timeout
        )
        if login_resp.status_code != 200:
            raise RuntimeError(f"Trader login failed for {email}: HTTP {login_resp.status_code} - {login_resp.text}")

        # Mint chart token using session cookie
        token_resp = auth_session.post(
            f"{self.base_url}/api/auth/chart-token",
            timeout=self.timeout
        )
        if token_resp.status_code != 200:
            raise RuntimeError(f"Failed to mint chart token for {email}: HTTP {token_resp.status_code} - {token_resp.text}")

        token = token_resp.json().get("token")
        with self._lock:
            self._tokens[email] = token
        return token

    # -------------------------------------------------------------------------
    # OMS API Calls (Paper / Real)
    # -------------------------------------------------------------------------
    def get_positions(self, email: str, instance: str = "paper") -> Dict[str, Any]:
        """Fetch all open positions and current funds for an account."""
        token = self.get_trader_token(email)
        headers = {"Authorization": f"Bearer {token}", "X-Broker-ID": instance}
        resp = self.request_with_retry("GET", f"{self.base_url}/v1/oms/{instance}/positions", headers=headers)
        if resp.status_code == 401:
            token = self.get_trader_token(email, force_refresh=True)
            headers["Authorization"] = f"Bearer {token}"
            resp = self.request_with_retry("GET", f"{self.base_url}/v1/oms/{instance}/positions", headers=headers)
        if resp.status_code != 200:
            return {"count": 0, "positions": [], "funds": {}, "error": resp.text}
        return resp.json()

    def get_orders(self, email: str, instance: str = "paper") -> Dict[str, Any]:
        """Fetch all orders (active / pending / recent) for an account."""
        token = self.get_trader_token(email)
        headers = {"Authorization": f"Bearer {token}", "X-Broker-ID": instance}
        resp = self.request_with_retry("GET", f"{self.base_url}/v1/oms/{instance}/orders", headers=headers)
        if resp.status_code == 401:
            token = self.get_trader_token(email, force_refresh=True)
            headers["Authorization"] = f"Bearer {token}"
            resp = self.request_with_retry("GET", f"{self.base_url}/v1/oms/{instance}/orders", headers=headers)
        if resp.status_code != 200:
            return {"count": 0, "orders": [], "error": resp.text}
        return resp.json()

    def get_history(self, email: str, instance: str = "paper") -> Dict[str, Any]:
        """Fetch closed trade history for an account."""
        token = self.get_trader_token(email)
        headers = {"Authorization": f"Bearer {token}", "X-Broker-ID": instance}
        resp = self.request_with_retry("GET", f"{self.base_url}/v1/oms/{instance}/history", headers=headers)
        if resp.status_code == 401:
            token = self.get_trader_token(email, force_refresh=True)
            headers["Authorization"] = f"Bearer {token}"
            resp = self.request_with_retry("GET", f"{self.base_url}/v1/oms/{instance}/history", headers=headers)
        if resp.status_code != 200:
            return {"count": 0, "history": [], "error": resp.text}
        return resp.json()

    def place_order(
        self,
        email: str,
        symbol: str = "BINANCE:BTCUSDT.P",
        side: str = "BUY",
        order_type: str = "MARKET",
        qty: float = 1.0,
        price: Optional[float] = None,
        tp: Optional[float] = None,
        sl: Optional[float] = None,
        instance: str = "paper"
    ) -> Dict[str, Any]:
        """Place market or pending order."""
        token = self.get_trader_token(email)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Broker-ID": instance
        }
        endpoint = "/orders/pending" if order_type.upper() in ["LIMIT", "STOP"] else "/orders"
        payload: Dict[str, Any] = {
            "symbol": symbol,
            "side": side.upper(),
            "type": order_type.upper(),
            "qty": qty
        }
        if price is not None:
            payload["price"] = price
        if tp is not None:
            payload["tp"] = tp
        if sl is not None:
            payload["sl"] = sl

        resp = self.request_with_retry("POST", f"{self.base_url}/v1/oms/{instance}{endpoint}", headers=headers, json=payload)
        return {"status_code": resp.status_code, "data": resp.json() if resp.status_code == 200 else resp.text}

    def set_position_protection(
        self,
        email: str,
        market_order_id: str,
        tp: Optional[float] = None,
        sl: Optional[float] = None,
        instance: str = "paper"
    ) -> Dict[str, Any]:
        """Set or modify Take Profit / Stop Loss on an open position."""
        token = self.get_trader_token(email)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Broker-ID": instance
        }
        payload: Dict[str, Any] = {}
        if tp is not None:
            payload["tp"] = tp
        if sl is not None:
            payload["sl"] = sl

        url = f"{self.base_url}/v1/oms/{instance}/positions/{market_order_id}/protection"
        resp = self.request_with_retry("PUT", url, headers=headers, json=payload)
        return {"status_code": resp.status_code, "data": resp.json() if resp.status_code == 200 else resp.text}

    def squareoff_position(self, email: str, market_order_id: str, instance: str = "paper") -> Dict[str, Any]:
        """Close an open position completely."""
        token = self.get_trader_token(email)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Broker-ID": instance
        }
        url = f"{self.base_url}/v1/oms/{instance}/positions/{market_order_id}/squareoff"
        resp = self.request_with_retry("POST", url, headers=headers, json={})
        return {"status_code": resp.status_code, "data": resp.json() if resp.status_code == 200 else resp.text}

    def reduce_position(self, email: str, market_order_id: str, qty: float, instance: str = "paper") -> Dict[str, Any]:
        """Partially close an open position."""
        token = self.get_trader_token(email)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Broker-ID": instance
        }
        url = f"{self.base_url}/v1/oms/{instance}/positions/{market_order_id}/reduce"
        resp = self.request_with_retry("POST", url, headers=headers, json={"qty": qty})
        return {"status_code": resp.status_code, "data": resp.json() if resp.status_code == 200 else resp.text}

    def cancel_order(self, email: str, order_id: str, instance: str = "paper") -> Dict[str, Any]:
        """Cancel a pending order."""
        token = self.get_trader_token(email)
        headers = {"Authorization": f"Bearer {token}", "X-Broker-ID": instance}
        url = f"{self.base_url}/v1/oms/{instance}/orders/{order_id}"
        resp = self.request_with_retry("DELETE", url, headers=headers)
        return {"status_code": resp.status_code, "data": resp.json() if resp.status_code == 200 else resp.text}

    def bulk_squareoff(self, email: str, instance: str = "paper") -> Dict[str, Any]:
        """Close all open positions for an account."""
        pos_res = self.get_positions(email, instance)
        positions = pos_res.get("positions", [])
        if not positions:
            return {"status_code": 200, "data": {"message": "No open positions"}}

        mkt_ids = [p.get("market_order_id") for p in positions if p.get("market_order_id")]
        if not mkt_ids:
            return {"status_code": 200, "data": {"message": "No open positions to close"}}

        token = self.get_trader_token(email)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Broker-ID": instance
        }
        url = f"{self.base_url}/v1/oms/{instance}/positions/bulk/squareoff"
        resp = self.request_with_retry("POST", url, headers=headers, json={"market_order_ids": mkt_ids})
        return {"status_code": resp.status_code, "data": resp.json() if resp.status_code == 200 else resp.text}

    def bulk_cancel(self, email: str, instance: str = "paper") -> Dict[str, Any]:
        """Cancel all pending orders for an account."""
        orders_res = self.get_orders(email, instance)
        orders = orders_res.get("orders", [])
        pending_ids = [
            o.get("order_id") for o in orders 
            if o.get("status") in ["PENDING", "OPEN", "NEW"] or o.get("type") in ["LIMIT", "STOP"]
        ]
        if not pending_ids:
            return {"status_code": 200, "data": {"message": "No pending orders"}}

        token = self.get_trader_token(email)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Broker-ID": instance
        }
        url = f"{self.base_url}/v1/oms/{instance}/orders/bulk/cancel"
        resp = self.request_with_retry("POST", url, headers=headers, json={"order_ids": pending_ids})
        return {"status_code": resp.status_code, "data": resp.json() if resp.status_code == 200 else resp.text}

    # -------------------------------------------------------------------------
    # Copy Trading API Calls
    # -------------------------------------------------------------------------
    def follow_master(
        self,
        email: str,
        master_client_id: str,
        instance: str = "paper",
        method: str = "multiplier",
        multiplier: float = 1.0,
        reverse: bool = False,
        copy_mode: str = "public"
    ) -> Dict[str, Any]:
        """Follow a master trader with specific multiplier and copy settings."""
        token = self.get_trader_token(email)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        payload = {
            "master_client_id": master_client_id,
            "method": method,
            "multiplier": multiplier,
            "reverse": reverse,
            "copy_mode": copy_mode
        }
        url = f"{self.base_url}/v1/oms/{instance}/copy/follow"
        resp = self.request_with_retry("POST", url, headers=headers, json=payload)
        return {"status_code": resp.status_code, "data": resp.json() if resp.status_code == 200 else resp.text}

    def unfollow_master(self, email: str, master_client_id: str, instance: str = "paper") -> Dict[str, Any]:
        """Unfollow a master trader."""
        token = self.get_trader_token(email)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        url = f"{self.base_url}/v1/oms/{instance}/copy/unfollow"
        resp = self.request_with_retry("POST", url, headers=headers, json={"master_client_id": master_client_id})
        return {"status_code": resp.status_code, "data": resp.json() if resp.status_code == 200 else resp.text}

    def get_copy_followers(self, master_email: str, instance: str = "paper", active_only: bool = True) -> List[Dict[str, Any]]:
        """Fetch all followers linked to this master (optionally filtering for active status)."""
        token = self.get_trader_token(master_email)
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{self.base_url}/v1/oms/{instance}/copy/follows"
        resp = self.request_with_retry("GET", url, headers=headers)
        if resp.status_code == 200:
            followers = resp.json().get("followers", [])
            if active_only:
                return [f for f in followers if f.get("status") == "active"]
            return followers
        return []

    # -------------------------------------------------------------------------
    # High-Throughput Concurrent Read-Back (ThreadPoolExecutor)
    # -------------------------------------------------------------------------
    def fetch_all_followers_positions(self, follower_emails: List[str], instance: str = "paper") -> Dict[str, Dict[str, Any]]:
        """Concurrently fetch open positions and funds for all followers."""
        results: Dict[str, Dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_email = {executor.submit(self.get_positions, email, instance): email for email in follower_emails}
            for future in as_completed(future_to_email):
                email = future_to_email[future]
                try:
                    results[email] = future.result()
                except Exception as e:
                    results[email] = {"count": 0, "positions": [], "funds": {}, "error": str(e)}
        return results

    def fetch_all_followers_orders(self, follower_emails: List[str], instance: str = "paper") -> Dict[str, Dict[str, Any]]:
        """Concurrently fetch orders for all followers."""
        results: Dict[str, Dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_email = {executor.submit(self.get_orders, email, instance): email for email in follower_emails}
            for future in as_completed(future_to_email):
                email = future_to_email[future]
                try:
                    results[email] = future.result()
                except Exception as e:
                    results[email] = {"count": 0, "orders": [], "error": str(e)}
        return results

    def teardown_all_accounts(self, master_email: str, follower_emails: List[str], instance: str = "paper") -> None:
        """Teardown: squareoff all positions and cancel all pending orders for master + all followers."""
        print(f"[*] Teardown: Closing all positions and cancelling orders for Master & {len(follower_emails)} followers...")
        all_emails = [master_email] + follower_emails
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Bulk cancel
            list(executor.map(lambda em: self.bulk_cancel(em, instance), all_emails))
            # Bulk squareoff
            list(executor.map(lambda em: self.bulk_squareoff(em, instance), all_emails))
        print("[+] Teardown completed successfully. All accounts clean.")
