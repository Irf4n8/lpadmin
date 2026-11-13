#!/usr/bin/env python3
"""
BlackTrader Social Trading Unified Real-Time QA & Monitoring Dashboard (v3.0 ENTERPRISE)
========================================================================================
Serves a high-performance, sleek trading terminal dashboard on http://localhost:8500

New Features Added:
1. Summary Cards for Profit Shared to Master:
   - Total Profit Shared to Master by all followers ($)
   - Total Profit Retained by followers ($)
   - Master Total Trading Profit ($)
   - Overall Social Pool Net Profit ($)
2. Follower Table Enhancements:
   - Correct Benchmark (HWM) from /mam/follows (no more $0.00)
   - "Following" column showing manager name & agreed share % (e.g., mammaster (50%))
   - "Total Profit Shared to Master" column tracking exact contribution per follower
   - "Total Profit Kept" column tracking follower's net retained profit
3. Click-to-View Follower Order History Modal:
   - Clicking any follower row opens a sleek interactive modal
   - Shows order-by-order trade breakdown with Gross P&L, Above Benchmark check, Manager Share (50%), and Follower Kept
4. Separated Dedicated Tabs:
   - Master Active Positions
   - Followers Active Positions
   - Follower Accounts, Balances & Profit Shares
   - Closed Trade History & Execution Ledger
5. Multi-Master Selector (MAM Master, Copy Trading Master, PAMM Master)
"""

import os
import sys
import time
import json
import re
import argparse
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import threading
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
import requests
import concurrent.futures

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_BASE_URL = "https://lpadmin.blackfx.com"
DEFAULT_PASSWORD = "Test@1234"

MASTERS_CONFIG = {
    "mam": {
        "id": "mam",
        "name": "MAM Master (Multi-Account Manager)",
        "email": "mammaster@mailinator.com",
        "client_id": "mem_e2dbce29e1c71a7bf6",
        "type": "MAM",
        "follower_prefix": "mamfollower",
        "follower_domain": "mailinator.com",
        "follower_count": 100
    }
}


def load_env_file(filepath: str = ".env") -> dict:
    env = {}
    path = BASE_DIR / filepath
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
    return env


# Hedging = paper / real, Netting = paper-net / real-net (separate OMS instances; an account follows on one at a time)
ALL_INSTANCES = ["paper", "paper-net", "real", "real-net"]

class TraderSession:
    def __init__(self, email: str, password: str, name: str, base_url: str = DEFAULT_BASE_URL, role: str = "follower"):
        self.email = email
        self.password = password
        self.name = name
        self.role = role
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.chart_token: Optional[str] = None
        self.member_id: Optional[str] = None
        self.last_auth_time = 0

    def authenticate(self) -> bool:
        login_url = f"{self.base_url}/api/auth/login"
        try:
            r = self.session.post(login_url, json={"email": self.email, "password": self.password}, timeout=15)
            if r.status_code == 200 and r.json().get("success"):
                login_data = r.json()
                trader = login_data.get("trader") or {}
                self.member_id = trader.get("member_id") or login_data.get("client_id")
                tok_res = self.session.post(f"{self.base_url}/api/auth/chart-token", timeout=15)
                if tok_res.status_code == 200:
                    data = tok_res.json()
                    self.chart_token = data.get("token")
                    if not self.member_id:
                        user = data.get("user") or {}
                        self.member_id = user.get("id") or user.get("client_id")
                    self.last_auth_time = time.time()
                    return True
        except Exception:
            pass
        return False

    def ensure_auth(self):
        if not self.chart_token or (time.time() - self.last_auth_time > 3600):
            self.authenticate()

    def get_headers(self) -> dict:
        self.ensure_auth()
        return {
            "Authorization": f"Bearer {self.chart_token}",
            "Content-Type": "application/json"
        }

    def get_funds(self, instance: str = "paper") -> dict:
        try:
            r = self.session.get(f"{self.base_url}/v1/oms/{instance}/funds", headers=self.get_headers(), timeout=8)
            if r.status_code == 200:
                return r.json().get("funds", {})
        except Exception:
            pass
        return {}

    def get_positions(self, instance: str = "paper") -> list:
        try:
            r = self.session.get(f"{self.base_url}/v1/oms/{instance}/positions", headers=self.get_headers(), timeout=8)
            if r.status_code == 200:
                return r.json().get("positions", [])
        except Exception:
            pass
        return []

    def get_history(self, instance: str = "paper") -> list:
        try:
            r = self.session.get(f"{self.base_url}/v1/oms/{instance}/history", headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                return r.json().get("history", [])
        except Exception:
            pass
        return []

    def get_mam_follows(self, instance: str = "paper") -> dict:
        try:
            r = self.session.get(f"{self.base_url}/v1/oms/{instance}/mam/follows", headers=self.get_headers(), timeout=8)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return {}

    def get_mam_shares(self, instance: str = "paper") -> dict:
        url = f"{self.base_url}/v1/oms/{instance}/mam/shares"
        if self.role == "master":
            url += "?role=master"
        try:
            r = self.session.get(url, headers=self.get_headers(), timeout=8)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return {}

    def unfollow_mam_master(self, master_client_id: str, follow_id: Optional[str] = None, instance: str = "paper") -> bool:
        headers = self.get_headers()
        payload = {"master_client_id": master_client_id}
        if follow_id:
            payload["follow_id"] = follow_id
        url = f"{self.base_url}/v1/oms/{instance}/mam/unfollow"
        try:
            r = self.session.post(url, json=payload, headers=headers, timeout=12)
            if r.status_code == 200:
                return True
            r2 = self.session.post(f"{self.base_url}/v1/oms/{instance}/copy/unfollow", json=payload, headers=headers, timeout=12)
            return r2.status_code == 200
        except Exception:
            return False

    def follow_mam_master(self, master_client_id: str, method: str, multiplier: float = 1.0, share_percent: float = 50.0, instance: str = "paper") -> bool:
        headers = self.get_headers()
        payload = {
            "master_client_id": master_client_id,
            "method": method,
            "multiplier": float(multiplier),
            "share_percent": float(share_percent),
            "reverse": False,
            "copy_mode": "public"
        }
        url = f"{self.base_url}/v1/oms/{instance}/mam/follow"
        try:
            r = self.session.post(url, json=payload, headers=headers, timeout=12)
            if r.status_code == 200:
                return True
            r2 = self.session.post(f"{self.base_url}/v1/oms/{instance}/copy/follow", json=payload, headers=headers, timeout=12)
            return r2.status_code == 200
        except Exception:
            return False

    def update_mam_master_settings(self, share_percent: float, display_name: Optional[str] = None, instance: str = "paper") -> Tuple[bool, dict]:
        headers = self.get_headers()
        url = f"{self.base_url}/v1/oms/{instance}/mam/master"
        payload = {
            "share_percent": float(share_percent)
        }
        if display_name:
            payload["display_name"] = display_name
        else:
            payload["display_name"] = self.email.split("@")[0]

        try:
            r = self.session.post(url, json=payload, headers=headers, timeout=12)
            if r.status_code == 200 and r.json().get("success"):
                return True, r.json()
            return False, r.json() if r.status_code == 200 else {"error": f"HTTP {r.status_code}: {r.text}"}
        except Exception as e:
            return False, {"error": str(e)}


class MasterFollowerGroup:
    def __init__(self, cfg: dict, base_url: str, password: str):
        self.cfg = cfg
        self.id = cfg["id"]
        self.name = cfg["name"]
        self.master_email = cfg["email"]
        self.master_client_id = cfg.get("client_id", "")
        self.base_url = base_url
        self.password = password
        self.follower_count = cfg["follower_count"]
        self.instance = "paper"

        self.master_session = TraderSession(self.master_email, self.password, f"Master-{self.id}", self.base_url, role="master")
        self.follower_sessions: Dict[str, TraderSession] = {}
        if self.follower_count > 0:
            for i in range(1, self.follower_count + 1):
                email = f"{cfg['follower_prefix']}{i}@{cfg['follower_domain']}"
                self.follower_sessions[email] = TraderSession(email, self.password, f"f{i}", self.base_url, role="follower")

        self.cache: Dict[str, Any] = {
            "master": {},
            "followers": [],
            "master_positions": [],
            "follower_positions": [],
            "history": [],
            "summary": {}
        }


class MultiMasterDashboardManager:
    def __init__(self, base_url: str, password: str):
        self.base_url = base_url
        self.password = password
        self.instance = "paper"
        self.groups: Dict[str, MasterFollowerGroup] = {}
        for m_id, cfg in MASTERS_CONFIG.items():
            self.groups[m_id] = MasterFollowerGroup(cfg, self.base_url, self.password)

        self.lock = threading.Lock()
        self.is_running = True
        self.last_update_str = "--:--:--"

    def authenticate_all(self):
        print("[*] Authenticating all Masters & Followers in parallel...")
        all_sessions = []
        for g in self.groups.values():
            all_sessions.append(g.master_session)
            all_sessions.extend(g.follower_sessions.values())

        with concurrent.futures.ThreadPoolExecutor(max_workers=35) as executor:
            futures = [executor.submit(s.authenticate) for s in all_sessions]
            concurrent.futures.wait(futures)
        print(f"[+] All {len(all_sessions)} sessions authenticated.")

    @staticmethod
    def _empty_cache() -> Dict[str, Any]:
        return {"master": {}, "followers": [], "master_positions": [], "follower_positions": [], "history": [], "summary": {}}

    def update_single_group(self, g: MasterFollowerGroup):
        inst_at_start = self.instance
        try:
            # 1. Master Data & Shares
            m_funds = g.master_session.get_funds(self.instance)
            m_pos = g.master_session.get_positions(self.instance)
            m_raw_hist = g.master_session.get_history(self.instance)
            m_hist = []
            for h in m_raw_hist:
                h_copy = h.copy()
                h_copy["category"] = "master"
                h_copy["method"] = "master"
                h_copy["type"] = (h.get("entry_type") or h.get("type") or "MARKET").upper()
                h_copy["qty"] = float(h.get("qty") or 0.0)
                h_copy["tp"] = h.get("tp_price") or h.get("tp") or h.get("take_profit")
                h_copy["sl"] = h.get("sl_price") or h.get("sl") or h.get("stop_loss")
                h_copy["tsl"] = (
                    h.get("tsl") or 
                    h.get("tsl_price") or 
                    h.get("trailing_stop") or 
                    h.get("trailing_stop_loss") or 
                    h.get("trailing_distance") or 
                    h.get("trailing_trigger_price")
                )
                m_hist.append(h_copy)
            m_shares_res = g.master_session.get_mam_shares(self.instance) if g.id == "mam" else {}
            master_earned_shares = float(m_shares_res.get("master_share_total", 0.0))

            m_mam_data = g.master_session.get_mam_follows(self.instance) if g.id == "mam" else {}
            m_master_info = m_mam_data.get("master") or {}
            m_share_pct = float(m_master_info.get("share_percent", 50.0))
            m_disp_name = m_master_info.get("display_name", g.master_email.split("@")[0])

            master_data = {
                "id": g.id,
                "name": g.name,
                "email": g.master_email,
                "type": g.cfg["type"],
                "member_id": g.master_session.member_id or g.master_client_id,
                "balance": m_funds.get("balance", 0.0),
                "equity": m_funds.get("equity", 0.0),
                "unrealized_pnl": m_funds.get("unrealized_pnl", 0.0),
                "free_margin": m_funds.get("free_margin", 0.0),
                "used_margin": m_funds.get("used_margin", 0.0),
                "open_positions_count": len(m_pos),
                "profit_shares_earned": master_earned_shares,
                "mam_share_percent": m_share_pct,
                "mam_display_name": m_disp_name,
                "mam_status": m_master_info.get("status", "active")
            }

            # 2. Fetch Admin Members List (for Authoritative Book & Dual Balances)
            admin_members_map = {}
            try:
                admin_email = os.getenv("ADMIN_ID", "lpadmin@blacktrader.com")
                admin_pwd = os.getenv("ADMIN_PASSWORD", "Raj1234!")
                adm_sess = requests.Session()
                adm_r = adm_sess.post(f"{self.base_url}/admin/api/login", json={"email": admin_email, "password": admin_pwd, "remember": True}, timeout=10)
                if adm_r.status_code == 200:
                    adm_t = adm_r.json().get("token")
                    m_arr = adm_sess.get(f"{self.base_url}/admin/api/members", headers={"Authorization": f"Bearer {adm_t}"}, timeout=10).json().get("members", [])
                    for m_item in m_arr:
                        admin_members_map[m_item.get("email")] = m_item
            except Exception:
                pass

            followers_list = []
            follower_positions = []

            def fetch_follower(email: str, s: TraderSession) -> dict:
                funds = s.get_funds(self.instance)
                pos = s.get_positions(self.instance)
                bal = float(funds.get("balance", 0.0))
                eq = float(funds.get("equity", 0.0))
                unrealized = float(funds.get("unrealized_pnl", 0.0))
                total_lots = sum(float(p.get("net_qty", p.get("qty", 0))) for p in pos)

                # Fetch follow relationship & shares
                follows_data = s.get_mam_follows(self.instance) if g.id == "mam" else {}
                following_list = follows_data.get("following", [])
                active_follows = [fol for fol in following_list if fol.get("status") == "active"]
                follow_obj = active_follows[0] if active_follows else {}
                is_following = bool(active_follows)

                starting_balance = float(follow_obj.get("starting_balance", 10000000.0 if g.id == "mam" else 100000000.0))
                share_pct = float(follow_obj.get("share_percent", 50.0))
                method = follow_obj.get("method", "multiplier") if is_following else "unfollowed"
                multiplier = float(follow_obj.get("multiplier", 1.0)) if is_following else 0.0
                following_manager = g.master_email if is_following else "None (Unfollowed)"

                # Fetch MAM profit shares on follower
                shares_data = s.get_mam_shares(self.instance) if g.id == "mam" else {}
                shared_to_master_total = float(shares_data.get("master_share_total", 0.0))
                raw_shares = shares_data.get("shares", [])

                # Enrich shares history with trade details (symbol, side, qty, master_qty, order_type, tp, sl)
                f_hist = s.get_history(self.instance)
                f_hist_map = {item.get("history_id"): item for item in f_hist if item.get("history_id")}

                shares_history = []
                for sh in raw_shares:
                    sh_copy = sh.copy()
                    tid = sh.get("trade_id")
                    h_item = f_hist_map.get(tid, {})
                    
                    # Match master closed trade if available
                    m_match = None
                    if sh.get("at"):
                        sh_time = str(sh.get("at"))[:19]
                        for mh in m_hist:
                            if (mh.get("executed_at") or "").startswith(sh_time):
                                m_match = mh
                                break

                    sh_copy["symbol"] = h_item.get("symbol") or (m_match.get("symbol") if m_match else "BINANCE:BTCUSDT.P")
                    sh_copy["side"] = (h_item.get("side") or (m_match.get("side") if m_match else "BUY")).upper()
                    sh_copy["type"] = (h_item.get("entry_type") or h_item.get("type") or (m_match.get("type") if m_match else "MARKET")).upper()
                    f_lot = float(h_item.get("qty") or h_item.get("net_qty") or 0.0)
                    if f_lot == 0.0 and m_match:
                        f_lot = round(float(m_match.get("qty", 1.0)) * multiplier, 2)
                    sh_copy["qty"] = f_lot
                    sh_copy["master_qty"] = round(f_lot / multiplier, 2) if multiplier > 0 else (m_match.get("qty") if m_match else f_lot)

                    tp_val = h_item.get("tp_price") or h_item.get("tp") or h_item.get("take_profit") or (m_match.get("tp") if m_match else None)
                    sl_val = h_item.get("sl_price") or h_item.get("sl") or h_item.get("stop_loss") or (m_match.get("sl") if m_match else None)
                    tsl_val = (
                        h_item.get("tsl") or 
                        h_item.get("tsl_price") or 
                        h_item.get("trailing_stop") or 
                        h_item.get("trailing_stop_loss") or 
                        h_item.get("trailing_distance") or 
                        (m_match.get("tsl") if m_match else None)
                    )
                    sh_copy["tp"] = tp_val
                    sh_copy["sl"] = sl_val
                    sh_copy["tsl"] = tsl_val
                    sh_copy["entry_price"] = h_item.get("entry_price") or (m_match.get("entry_price") if m_match else None)
                    sh_copy["exit_price"] = h_item.get("exit_price") or (m_match.get("exit_price") if m_match else None)
                    sh_copy["category"] = method
                    sh_copy["method"] = method
                    sh_copy["multiplier"] = multiplier
                    shares_history.append(sh_copy)

                # Follower's profit kept
                total_kept = sum(float(sh.get("follower_share", 0.0)) for sh in shares_history)
                if not total_kept and bal > starting_balance:
                    total_kept = bal - starting_balance

                is_above_hwm = (bal > starting_balance)

                adm_info = admin_members_map.get(email, {})
                f_book = adm_info.get("book", "b")
                adm_bals = adm_info.get("balances", {})
                paper_bal = float(adm_bals.get("paper", bal if self.instance == "paper" else 10000000.0))
                real_bal = float(adm_bals.get("real", bal if self.instance == "real" else 0.0))
                broker_setting = follow_obj.get("instance") or self.instance

                return {
                    "email": email,
                    "name": s.name,
                    "member_id": adm_info.get("member_id") or s.member_id or "N/A",
                    "book": f_book,
                    "broker_setting": broker_setting,
                    "paper_balance": paper_bal,
                    "real_balance": real_bal,
                    "balance": bal,
                    "equity": eq,
                    "benchmark": starting_balance,
                    "above_benchmark": is_above_hwm,
                    "is_following": is_following,
                    "following": f"{following_manager} ({int(share_pct)}% share)" if is_following else "Not Following (Unfollowed)",
                    "manager_email": following_manager,
                    "share_percent": share_pct,
                    "method": method,
                    "multiplier": multiplier,
                    "shared_to_master": shared_to_master_total,
                    "profit_kept": total_kept,
                    "open_positions_count": len(pos),
                    "open_lots": total_lots,
                    "unrealized_pnl": unrealized,
                    "positions": pos,
                    "shares_history": shares_history
                }

            if g.follower_sessions:
                with concurrent.futures.ThreadPoolExecutor(max_workers=35) as executor:
                    future_to_f = {
                        executor.submit(fetch_follower, email, s): email
                        for email, s in g.follower_sessions.items()
                    }
                    for future in concurrent.futures.as_completed(future_to_f):
                        try:
                            res = future.result()
                            followers_list.append(res)
                        except Exception:
                            pass

            followers_list.sort(key=lambda x: int(re.search(r"\d+", x["email"]).group(0)) if re.search(r"\d+", x["email"]) else 0)

            # 3. Master Positions Tagged & Enriched
            master_positions = []
            master_positions_map = {}
            for p in m_pos:
                p_copy = p.copy()
                p_copy["account"] = g.master_email
                p_copy["role"] = "master"
                p_copy["category"] = "master"
                p_copy["method"] = "master"
                m_qty = float(p.get("net_qty") or p.get("qty") or p.get("lot") or 0.0)
                p_copy["qty"] = m_qty
                p_copy["net_qty"] = m_qty
                p_copy["type"] = (p.get("type") or p.get("order_type") or "MARKET").upper()
                p_tp = (
                    p.get("tp") or 
                    p.get("take_profit") or 
                    (p.get("tp_order") or {}).get("trigger_price") or 
                    (p.get("tp_order") or {}).get("price")
                )
                p_sl = (
                    p.get("sl") or 
                    p.get("stop_loss") or 
                    (p.get("sl_order") or {}).get("trigger_price") or 
                    (p.get("sl_order") or {}).get("price")
                )
                p_copy["tp"] = p_tp or p.get("tp_price")
                p_copy["sl"] = p_sl or p.get("sl_price")
                p_copy["tsl"] = (
                    p.get("tsl") or 
                    p.get("tsl_price") or 
                    p.get("trailing_stop") or 
                    p.get("trailing_stop_loss") or 
                    p.get("trailing_distance") or 
                    (p.get("tsl_order") or {}).get("trigger_price") or 
                    (p.get("trailing_order") or {}).get("trigger_price")
                )
                p_copy["time"] = p.get("created_at") or p.get("time") or p.get("open_time") or p.get("updated_at") or "--"
                master_positions.append(p_copy)
                master_positions_map[p.get("symbol")] = p_copy

            # 4. Follower Positions Tagged & Enriched
            follower_positions = []
            for res in followers_list:
                for p in res.get("positions", []):
                    p_copy = p.copy()
                    p_copy["account"] = res["email"]
                    p_copy["role"] = "follower"
                    p_copy["category"] = res.get("method", "multiplier")
                    p_copy["method"] = res.get("method", "multiplier")
                    mult = float(res.get("multiplier", 1.0))
                    p_copy["multiplier"] = mult
                    f_qty = float(p.get("net_qty") or p.get("qty") or p.get("lot") or 0.0)
                    p_copy["qty"] = f_qty
                    p_copy["net_qty"] = f_qty
                    p_copy["type"] = (p.get("type") or p.get("order_type") or "MARKET").upper()
                    # Reference Master Lot Size & Bracket Parameters
                    m_match = master_positions_map.get(p.get("symbol"))
                    if m_match:
                        p_copy["master_qty"] = m_match.get("qty", 0.0)
                    else:
                        p_copy["master_qty"] = round(f_qty / mult, 2) if mult > 0 else f_qty

                    f_tp = (
                        p.get("tp") or 
                        p.get("tp_price") or 
                        p.get("take_profit") or 
                        (p.get("tp_order") or {}).get("trigger_price") or 
                        (p.get("tp_order") or {}).get("price")
                    )
                    f_sl = (
                        p.get("sl") or 
                        p.get("sl_price") or 
                        p.get("stop_loss") or 
                        (p.get("sl_order") or {}).get("trigger_price") or 
                        (p.get("sl_order") or {}).get("price")
                    )
                    if not f_tp and m_match:
                        f_tp = m_match.get("tp")
                    if not f_sl and m_match:
                        f_sl = m_match.get("sl")

                    f_tsl = (
                        p.get("tsl") or 
                        p.get("tsl_price") or 
                        p.get("trailing_stop") or 
                        p.get("trailing_stop_loss") or 
                        p.get("trailing_distance") or 
                        (p.get("tsl_order") or {}).get("trigger_price") or 
                        (p.get("trailing_order") or {}).get("trigger_price")
                    )
                    if not f_tsl and m_match:
                        f_tsl = m_match.get("tsl")

                    p_copy["tp"] = f_tp
                    p_copy["sl"] = f_sl
                    p_copy["tsl"] = f_tsl
                    p_copy["time"] = p.get("created_at") or p.get("time") or p.get("open_time") or p.get("updated_at") or "--"
                    follower_positions.append(p_copy)

            # 5. Global Summaries & Totals
            tot_f_bal = sum(f["balance"] for f in followers_list)
            tot_f_eq = sum(f["equity"] for f in followers_list)
            tot_f_pos = sum(f["open_positions_count"] for f in followers_list)
            tot_f_pnl = sum(f["unrealized_pnl"] for f in followers_list)

            # Open lots
            total_master_open_lots = sum(p["qty"] for p in master_positions)
            tot_follower_open_lots = sum(p["qty"] for p in follower_positions)

            # Sum of all profit shared to master across all followers
            tot_shared_to_master_by_followers = sum(f["shared_to_master"] for f in followers_list)
            tot_profit_kept_by_followers = sum(f["profit_kept"] for f in followers_list)
            followers_above_hwm_count = sum(1 for f in followers_list if f["above_benchmark"])

            expected_copies = len(m_pos) * len(followers_list)
            rep_rate = round((tot_f_pos / expected_copies) * 100, 1) if expected_copies > 0 else 100.0

            # Win Rate Calculation from History
            wins = sum(1 for h in m_hist if float(h.get("realized_pnl", 0)) > 0)
            total_closed = len(m_hist)
            win_rate = round((wins / total_closed) * 100, 1) if total_closed > 0 else 0.0
            tot_master_realized_pnl = sum(float(h.get("realized_pnl", 0)) for h in m_hist)

            summary = {
                "master_balance": master_data["balance"],
                "master_equity": master_data["equity"],
                "master_trading_pnl": tot_master_realized_pnl,
                "master_shares_total": tot_shared_to_master_by_followers,
                "master_total_earnings": tot_master_realized_pnl + tot_shared_to_master_by_followers,
                "total_follower_balance": tot_f_bal,
                "total_follower_equity": tot_f_eq,
                "total_profit_kept_by_followers": tot_profit_kept_by_followers,
                "followers_above_hwm_count": followers_above_hwm_count,
                "total_follower_positions": tot_f_pos,
                "master_open_positions": len(m_pos),
                "master_open_lots": round(total_master_open_lots, 2),
                "total_follower_open_lots": round(tot_follower_open_lots, 2),
                "active_replication_rate": rep_rate,
                "total_closed_trades": total_closed,
                "win_rate_percent": win_rate,
                "follower_count": len(followers_list),
                "active_environment": self.instance,
                "a_book_count": sum(1 for f in followers_list if f.get("book") == "a"),
                "b_book_count": sum(1 for f in followers_list if f.get("book") != "a"),
                "real_broker_count": sum(1 for f in followers_list if str(f.get("broker_setting")) == "real"),
                "real_net_broker_count": sum(1 for f in followers_list if f.get("broker_setting") == "real-net"),
                "paper_broker_count": sum(1 for f in followers_list if not str(f.get("broker_setting")).startswith("real"))
            }

            if self.instance != inst_at_start:
                return  # environment was switched while this refresh ran - discard it instead of mixing paper/real data

            g.cache = {
                "master": master_data,
                "followers": followers_list,
                "master_positions": master_positions,
                "follower_positions": follower_positions,
                "history": m_hist,
                "summary": summary
            }
            g.last_error = None

        except Exception as exc:
            g.last_error = f"{type(exc).__name__}: {exc}"
            print(f"[!] refresh failed ({inst_at_start}): {g.last_error}")

    def handle_master_share_change(self, master_id: str, share_percent: float, display_name: Optional[str] = None) -> dict:
        g = self.groups.get(master_id) or self.groups.get("mam")
        if not g:
            return {"success": False, "error": f"Master group '{master_id}' not found"}

        ok, res = g.master_session.update_mam_master_settings(
            share_percent=share_percent,
            display_name=display_name,
            instance=self.instance
        )

        if ok:
            # Trigger immediate background cache refresh
            threading.Thread(target=self.update_single_group, args=(g,)).start()
            return {
                "success": True,
                "master_email": g.master_email,
                "share_percent": share_percent,
                "display_name": display_name or g.master_email.split("@")[0],
                "details": res
            }
        else:
            return {
                "success": False,
                "error": res.get("error") if isinstance(res, dict) else "Failed to update master settings"
            }

    def handle_unfollow(self, target_type: str, start: int, end: int, single_email: str) -> dict:
        g = self.groups.get("mam")
        if not g:
            return {"success": False, "error": "MAM group not configured"}

        master_client_id = g.master_client_id

        target_sessions = []
        if target_type == "single":
            if single_email in g.follower_sessions:
                target_sessions.append(g.follower_sessions[single_email])
        elif target_type == "range":
            for i in range(start, end + 1):
                em = f"mamfollower{i}@mailinator.com"
                if em in g.follower_sessions:
                    target_sessions.append(g.follower_sessions[em])
        else:  # "all"
            target_sessions = list(g.follower_sessions.values())

        if not target_sessions:
            return {"success": False, "error": "No matching follower sessions found"}

        success_count = 0
        fail_count = 0
        details = []

        def worker(s: TraderSession):
            try:
                for inst in ALL_INSTANCES:
                    f_data = s.get_mam_follows(inst)
                    following_list = f_data.get("following", [])
                    for fol in following_list:
                        if fol.get("status") == "active":
                            s.unfollow_mam_master(master_client_id, follow_id=fol.get("follow_id"), instance=inst)
                return s.email, True
            except Exception as e:
                return s.email, False

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(worker, s) for s in target_sessions]
            for fut in concurrent.futures.as_completed(futures):
                em, ok = fut.result()
                if ok:
                    success_count += 1
                else:
                    fail_count += 1
                details.append({"email": em, "success": ok})

        # Trigger immediate background cache refresh
        threading.Thread(target=self.update_single_group, args=(g,)).start()

        return {
            "success": True,
            "total_targeted": len(target_sessions),
            "success_count": success_count,
            "fail_count": fail_count,
            "details": details
        }

    def handle_bulk_follow(self, target_type: str, start: int, end: int, single_email: str, category: str = "equity", multiplier: float = 1.0) -> dict:
        return self.handle_category_change(
            target_type=target_type,
            start=start,
            end=end,
            single_email=single_email,
            category=category,
            multiplier=multiplier
        )

    def handle_category_change(self, target_type: str, start: int, end: int, single_email: str, category: str, multiplier: float, share_percent: Optional[float] = None) -> dict:
        g = self.groups.get("mam")
        if not g:
            return {"success": False, "error": "MAM group not configured"}

        master_client_id = g.master_client_id

        if category in ["leave", "unfollowed"]:
            return self.handle_unfollow(target_type=target_type, start=start, end=end, single_email=single_email)

        # Use Master's official profit share if not explicitly provided
        if share_percent is None or share_percent <= 0:
            share_percent = float(g.cache.get("master", {}).get("mam_share_percent", 50.0))

        # Determine target follower sessions
        target_sessions = []
        if target_type == "single":
            if single_email in g.follower_sessions:
                target_sessions.append(g.follower_sessions[single_email])
        elif target_type == "range":
            for i in range(start, end + 1):
                em = f"mamfollower{i}@mailinator.com"
                if em in g.follower_sessions:
                    target_sessions.append(g.follower_sessions[em])
        else:  # "all"
            target_sessions = list(g.follower_sessions.values())

        if not target_sessions:
            return {"success": False, "error": "No matching follower sessions found"}

        success_count = 0
        fail_count = 0
        details = []

        def worker(s: TraderSession):
            try:
                # Follow on real if self.instance is paper (since OMS only allows copy trading on real instances)
                inst = self.instance if self.instance in ["real", "real-net"] else "real"
                # 1. Fetch current follows across instances to clean up previous follow
                for check_inst in ALL_INSTANCES:
                    f_data = s.get_mam_follows(check_inst)
                    following_list = f_data.get("following", [])
                    for fol in following_list:
                        if fol.get("status") == "active":
                            s.unfollow_mam_master(master_client_id, follow_id=fol.get("follow_id"), instance=check_inst)
                time.sleep(0.1)
                # 2. Follow with new configuration on real instance
                ok = s.follow_mam_master(master_client_id, method=category, multiplier=multiplier, share_percent=share_percent, instance=inst)
                return s.email, ok
            except Exception as e:
                return s.email, False

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(worker, s) for s in target_sessions]
            for fut in concurrent.futures.as_completed(futures):
                em, ok = fut.result()
                if ok:
                    success_count += 1
                else:
                    fail_count += 1
                details.append({"email": em, "success": ok})

        # Trigger immediate background cache refresh
        threading.Thread(target=self.update_single_group, args=(g,)).start()

        return {
            "success": True,
            "total_targeted": len(target_sessions),
            "success_count": success_count,
            "fail_count": fail_count,
            "category": category,
            "multiplier": multiplier,
            "details": details
        }

    def handle_environment_switch(self, instance: str) -> dict:
        inst = instance.lower()
        if inst not in ALL_INSTANCES:
            return {"success": False, "error": f"Invalid instance: {instance}"}
        if inst == self.instance:
            return {"success": True, "active_environment": inst, "unchanged": True}
        self.instance = inst
        for g in self.groups.values():
            g.instance = inst
            g.cache = self._empty_cache()
            g.last_error = None
            threading.Thread(target=self.update_single_group, args=(g,)).start()
        return {"success": True, "active_environment": inst}

    def handle_book_change(self, target_type: str, start: int, end: int, single_email: str, book: str) -> dict:
        g = self.groups.get("mam")
        if not g:
            return {"success": False, "error": "MAM group not configured"}

        target_sessions = []
        if target_type == "single":
            if single_email in g.follower_sessions:
                target_sessions.append(g.follower_sessions[single_email])
        elif target_type == "range":
            for i in range(start, end + 1):
                em = f"mamfollower{i}@mailinator.com"
                if em in g.follower_sessions:
                    target_sessions.append(g.follower_sessions[em])
        else:  # "all"
            target_sessions = list(g.follower_sessions.values())

        if not target_sessions:
            return {"success": False, "error": "No matching follower sessions found"}

        # Admin login
        admin_email = os.getenv("ADMIN_ID", "lpadmin@blacktrader.com")
        admin_pwd = os.getenv("ADMIN_PASSWORD", "Raj1234!")
        admin_session = requests.Session()
        adm_res = admin_session.post(
            f"{self.base_url}/admin/api/login",
            json={"email": admin_email, "password": admin_pwd, "remember": True},
            timeout=15
        )
        if adm_res.status_code != 200:
            return {"success": False, "error": f"Admin login failed: HTTP {adm_res.status_code}"}

        adm_token = adm_res.json().get("token")
        admin_session.headers.update({
            "Authorization": f"Bearer {adm_token}",
            "Content-Type": "application/json"
        })

        # Fetch admin members list to map email -> member_id
        member_map = {}
        try:
            m_list_res = admin_session.get(f"{self.base_url}/admin/api/members", timeout=12)
            if m_list_res.status_code == 200:
                for m in m_list_res.json().get("members", []):
                    member_map[m.get("email")] = m.get("member_id")
        except Exception:
            pass

        success_count = 0
        fail_count = 0
        details = []

        def worker(s: TraderSession):
            try:
                mem_id = member_map.get(s.email) or s.member_id
                if not mem_id or mem_id == "N/A":
                    s.ensure_auth()
                    mem_id = s.member_id
                if not mem_id:
                    return s.email, False, "Missing member_id"

                url = f"{self.base_url}/admin/api/members/{mem_id}/book"
                payload = {"book": book.lower()}
                r = admin_session.post(url, json=payload, timeout=12)
                ok = (r.status_code == 200 and r.json().get("success", False))
                return s.email, ok, r.text if not ok else "Success"
            except Exception as e:
                return s.email, False, str(e)

        with concurrent.futures.ThreadPoolExecutor(max_workers=25) as executor:
            futures = [executor.submit(worker, s) for s in target_sessions]
            for fut in concurrent.futures.as_completed(futures):
                em, ok, msg = fut.result()
                if ok:
                    success_count += 1
                else:
                    fail_count += 1
                details.append({"email": em, "success": ok, "message": msg})

        # Trigger immediate background cache refresh
        threading.Thread(target=self.update_single_group, args=(g,)).start()

        return {
            "success": True,
            "total_targeted": len(target_sessions),
            "success_count": success_count,
            "fail_count": fail_count,
            "book": book.lower(),
            "details": details
        }

    def handle_broker_setting_change(self, target_type: str, start: int, end: int, single_email: str, target_broker: str, action: str = "enable", category: str = "multiplier", multiplier: float = 2.0, share_percent: Optional[float] = None) -> dict:
        g = self.groups.get("mam")
        if not g:
            return {"success": False, "error": "MAM group not configured"}

        master_client_id = g.master_client_id
        target_inst = target_broker.lower()
        if target_inst not in ALL_INSTANCES:
            return {"success": False, "error": f"Invalid broker setting: {target_broker}"}

        if share_percent is None or share_percent <= 0:
            share_percent = float(g.cache.get("master", {}).get("mam_share_percent", 50.0))

        target_sessions = []
        if target_type == "single":
            if single_email in g.follower_sessions:
                target_sessions.append(g.follower_sessions[single_email])
        elif target_type == "range":
            for i in range(start, end + 1):
                em = f"mamfollower{i}@mailinator.com"
                if em in g.follower_sessions:
                    target_sessions.append(g.follower_sessions[em])
        else:  # "all"
            target_sessions = list(g.follower_sessions.values())

        if not target_sessions:
            return {"success": False, "error": "No matching follower sessions found"}

        # Admin login to sync account_type if enabling
        admin_session = None
        member_map = {}
        if action == "enable":
            try:
                admin_email = os.getenv("ADMIN_ID", "lpadmin@blacktrader.com")
                admin_pwd = os.getenv("ADMIN_PASSWORD", "Raj1234!")
                admin_session = requests.Session()
                adm_res = admin_session.post(
                    f"{self.base_url}/admin/api/login",
                    json={"email": admin_email, "password": admin_pwd, "remember": True},
                    timeout=15
                )
                if adm_res.status_code == 200:
                    adm_token = adm_res.json().get("token")
                    admin_session.headers.update({
                        "Authorization": f"Bearer {adm_token}",
                        "Content-Type": "application/json"
                    })
                    m_list_res = admin_session.get(f"{self.base_url}/admin/api/members", timeout=12)
                    if m_list_res.status_code == 200:
                        for m in m_list_res.json().get("members", []):
                            member_map[m.get("email")] = m.get("member_id")
            except Exception:
                pass

        success_count = 0
        fail_count = 0
        details = []

        def worker(s: TraderSession):
            try:
                if action == "enable":
                    # Update account_type in Admin API if needed
                    if target_inst in ["real", "real-net"] and admin_session and s.email in member_map:
                        mem_id = member_map[s.email]
                        try:
                            admin_session.post(f"{self.base_url}/admin/api/members/{mem_id}/account-type", json={"account_type": "live"}, timeout=8)
                        except Exception:
                            pass
                    elif target_inst in ["paper", "paper-net"] and admin_session and s.email in member_map:
                        mem_id = member_map[s.email]
                        try:
                            admin_session.post(f"{self.base_url}/admin/api/members/{mem_id}/account-type", json={"account_type": "demo"}, timeout=8)
                        except Exception:
                            pass

                    # Clean active follow on target_inst first if any
                    f_data = s.get_mam_follows(target_inst)
                    following_list = f_data.get("following", [])
                    for fol in following_list:
                        if fol.get("status") == "active":
                            s.unfollow_mam_master(master_client_id, follow_id=fol.get("follow_id"), instance=target_inst)
                    time.sleep(0.1)
                    # Follow on target_inst
                    ok = s.follow_mam_master(master_client_id, method=category, multiplier=multiplier, share_percent=share_percent, instance=target_inst)
                    return s.email, ok
                else:  # "disable"
                    # Unfollow active follow on target_inst
                    f_data = s.get_mam_follows(target_inst)
                    following_list = f_data.get("following", [])
                    for fol in following_list:
                        if fol.get("status") == "active":
                            s.unfollow_mam_master(master_client_id, follow_id=fol.get("follow_id"), instance=target_inst)
                    return s.email, True
            except Exception as e:
                return s.email, False

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(worker, s) for s in target_sessions]
            for fut in concurrent.futures.as_completed(futures):
                em, ok = fut.result()
                if ok:
                    success_count += 1
                else:
                    fail_count += 1
                details.append({"email": em, "success": ok})

        if action == "enable" and target_type == "all" and target_inst != self.instance:
            self.instance = target_inst
            g.instance = target_inst
            g.cache = self._empty_cache()

        # Trigger immediate background cache refresh
        threading.Thread(target=self.update_single_group, args=(g,)).start()

        return {
            "success": True,
            "action": action,
            "total_targeted": len(target_sessions),
            "success_count": success_count,
            "fail_count": fail_count,
            "target_broker": target_inst,
            "category": category,
            "multiplier": multiplier,
            "details": details
        }

    def handle_balance_change(self, target_type: str, start: int, end: int, single_email: str, balance: float, instance: str = "paper") -> dict:
        g = self.groups.get("mam")
        if not g:
            return {"success": False, "error": "MAM group not configured"}

        target_sessions = []
        is_master = False

        if target_type == "master" or single_email == g.master_email:
            target_sessions.append(g.master_session)
            is_master = True
        elif target_type == "single":
            if single_email in g.follower_sessions:
                target_sessions.append(g.follower_sessions[single_email])
        elif target_type == "range":
            for i in range(start, end + 1):
                em = f"mamfollower{i}@mailinator.com"
                if em in g.follower_sessions:
                    target_sessions.append(g.follower_sessions[em])
        else:  # "all"
            target_sessions = list(g.follower_sessions.values())

        if not target_sessions:
            return {"success": False, "error": "No matching sessions found"}

        # Admin login
        admin_email = os.getenv("ADMIN_ID", "lpadmin@blacktrader.com")
        admin_pwd = os.getenv("ADMIN_PASSWORD", "Raj1234!")
        admin_session = requests.Session()
        adm_res = admin_session.post(
            f"{self.base_url}/admin/api/login",
            json={"email": admin_email, "password": admin_pwd, "remember": True},
            timeout=15
        )
        if adm_res.status_code != 200:
            return {"success": False, "error": f"Admin login failed: HTTP {adm_res.status_code}"}

        adm_token = adm_res.json().get("token")
        admin_session.headers.update({
            "Authorization": f"Bearer {adm_token}",
            "Content-Type": "application/json"
        })

        # Fetch admin members list to map email -> member_id
        member_map = {}
        try:
            m_list_res = admin_session.get(f"{self.base_url}/admin/api/members", timeout=12)
            if m_list_res.status_code == 200:
                for m in m_list_res.json().get("members", []):
                    member_map[m.get("email")] = m.get("member_id")
        except Exception:
            pass

        success_count = 0
        fail_count = 0
        details = []

        instances_to_update = ["paper", "real"] if instance.lower() == "both" else [instance.lower()]

        def worker(s: TraderSession):
            try:
                mem_id = member_map.get(s.email) or s.member_id
                if not mem_id or mem_id == "N/A":
                    s.ensure_auth()
                    mem_id = s.member_id
                if not mem_id:
                    return s.email, False, "Missing member_id"

                url = f"{self.base_url}/admin/api/members/{mem_id}/balance"
                all_ok = True
                last_msg = "Success"
                for inst in instances_to_update:
                    payload = {
                        "instance": inst,
                        "balance": float(balance),
                        "remark": f"Dashboard Fleet Controller update ({inst})",
                        "force": True
                    }
                    r = admin_session.post(url, json=payload, timeout=12)
                    ok = (r.status_code == 200 and r.json().get("success", False))
                    if not ok:
                        all_ok = False
                        last_msg = r.text

                return s.email, all_ok, last_msg
            except Exception as e:
                return s.email, False, str(e)

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(worker, s) for s in target_sessions]
            for fut in concurrent.futures.as_completed(futures):
                em, ok, msg = fut.result()
                if ok:
                    success_count += 1
                else:
                    fail_count += 1
                details.append({"email": em, "success": ok, "message": msg})

        # Trigger immediate background cache refresh
        threading.Thread(target=self.update_single_group, args=(g,)).start()

        return {
            "success": True,
            "total_targeted": len(target_sessions),
            "success_count": success_count,
            "fail_count": fail_count,
            "target_instance": instance,
            "new_balance": balance,
            "details": details
        }

    def background_poller(self, interval: int = 1):
        self.authenticate_all()
        while self.is_running:
            for g in self.groups.values():
                self.update_single_group(g)
            with self.lock:
                self.last_update_str = datetime.now().strftime("%H:%M:%S")
            time.sleep(interval)


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


ENTERPRISE_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>BlackTrader Pro: Social Trading Unified Live OMS Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #07090e;
      --surface: #0f141f;
      --card-bg: #131a29;
      --card-border: #1e283d;
      --card-hover: #172033;
      --accent: #2563eb;
      --accent-bright: #3b82f6;
      --accent-glow: rgba(59, 130, 246, 0.25);
      --success: #10b981;
      --success-glow: rgba(16, 185, 129, 0.2);
      --danger: #f43f5e;
      --warning: #f59e0b;
      --cyan: #06b6d4;
      --purple: #a855f7;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --text-dim: #64748b;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg);
      color: var(--text);
      font-family: 'Plus Jakarta Sans', -apple-system, sans-serif;
      padding: 24px;
      line-height: 1.5;
      min-height: 100vh;
    }

    /* Top Bar */
    .top-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 20px;
      border-bottom: 1px solid var(--card-border);
      margin-bottom: 24px;
      flex-wrap: wrap;
      gap: 16px;
    }
    .brand-section {
      display: flex;
      align-items: center;
      gap: 16px;
    }
    .brand-badge {
      background: linear-gradient(135deg, #1d4ed8, #3b82f6);
      color: #fff;
      font-family: 'JetBrains Mono', monospace;
      font-weight: 800;
      font-size: 14px;
      padding: 8px 14px;
      border-radius: 8px;
      letter-spacing: 1px;
      box-shadow: 0 4px 15px var(--accent-glow);
    }
    .title-group h1 {
      font-size: 22px;
      font-weight: 800;
      color: #fff;
      letter-spacing: -0.5px;
    }
    .title-group p {
      font-size: 13px;
      color: var(--text-muted);
    }

    /* Master Selector Dropdown */
    .master-selector-wrapper {
      display: flex;
      align-items: center;
      gap: 12px;
      background: var(--surface);
      border: 1px solid var(--card-border);
      padding: 6px 14px;
      border-radius: 10px;
    }
    .master-select {
      background: transparent;
      border: none;
      color: #fff;
      font-size: 14px;
      font-weight: 700;
      cursor: pointer;
      outline: none;
      font-family: 'Plus Jakarta Sans', sans-serif;
    }
    .master-select option {
      background: #111827;
      color: #fff;
    }

    .top-controls {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .live-status {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 12px;
      font-weight: 700;
      color: var(--success);
      background: var(--success-glow);
      border: 1px solid rgba(16, 185, 129, 0.3);
      padding: 7px 14px;
      border-radius: 20px;
    }
    .pulse-dot {
      width: 8px;
      height: 8px;
      background: var(--success);
      border-radius: 50%;
      box-shadow: 0 0 10px var(--success);
      animation: pulse 1.6s infinite;
    }
    @keyframes pulse {
      0% { transform: scale(0.9); opacity: 0.8; }
      50% { transform: scale(1.2); opacity: 1; }
      100% { transform: scale(0.9); opacity: 0.8; }
    }
    .btn {
      background: var(--surface);
      border: 1px solid var(--card-border);
      color: #fff;
      font-size: 13px;
      font-weight: 600;
      padding: 8px 16px;
      border-radius: 8px;
      cursor: pointer;
      transition: all 0.2s;
    }
    .btn:hover { background: var(--card-hover); border-color: var(--text-dim); }
    .btn.active { background: var(--accent); border-color: var(--accent); }

    /* SUMMARY CARDS (Top Section with Profit Share Tracking) */
    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }
    .kpi-card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 18px 20px;
      position: relative;
      overflow: hidden;
      box-shadow: 0 4px 20px rgba(0,0,0,0.25);
    }
    .kpi-card::after {
      content: '';
      position: absolute;
      top: 0; left: 0; right: 0;
      height: 3px;
      background: linear-gradient(90deg, var(--accent-bright), transparent);
    }
    .kpi-card.gold::after {
      background: linear-gradient(90deg, #f59e0b, #fbbf24);
    }
    .kpi-card.green::after {
      background: linear-gradient(90deg, #10b981, #34d399);
    }
    .kpi-card.purple::after {
      background: linear-gradient(90deg, #a855f7, #c084fc);
    }
    .kpi-label {
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.8px;
      color: var(--text-muted);
      margin-bottom: 6px;
    }
    .kpi-val {
      font-family: 'JetBrains Mono', monospace;
      font-size: 22px;
      font-weight: 800;
      color: #fff;
    }
    .kpi-sub {
      font-size: 12px;
      color: var(--text-dim);
      margin-top: 4px;
    }
    .text-green { color: var(--success) !important; }
    .text-red { color: var(--danger) !important; }
    .text-cyan { color: var(--cyan) !important; }
    .text-gold { color: #f59e0b !important; }
    .text-purple { color: #c084fc !important; }

    /* Master Info Banner */
    .master-banner {
      background: linear-gradient(135deg, #0d1527, #131c33);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 18px 24px;
      margin-bottom: 24px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 18px;
    }
    .master-info-left {
      display: flex;
      align-items: center;
      gap: 16px;
    }
    .master-avatar {
      width: 48px;
      height: 48px;
      border-radius: 10px;
      background: linear-gradient(135deg, #1d4ed8, #06b6d4);
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 800;
      font-size: 18px;
      color: #fff;
    }
    .master-email-text {
      font-size: 16px;
      font-weight: 800;
      color: #fff;
    }
    .master-sub-text {
      font-size: 12px;
      color: var(--text-muted);
    }
    .master-metrics-right {
      display: flex;
      gap: 28px;
      flex-wrap: wrap;
    }
    .m-stat-title {
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--text-muted);
    }
    .m-stat-val {
      font-family: 'JetBrains Mono', monospace;
      font-size: 17px;
      font-weight: 700;
      color: #fff;
    }

    /* Dedicated Tabs Bar */
    .tabs-bar {
      display: flex;
      gap: 10px;
      border-bottom: 1px solid var(--card-border);
      margin-bottom: 22px;
      overflow-x: auto;
    }
    .tab-item {
      background: none;
      border: none;
      color: var(--text-muted);
      font-size: 14px;
      font-weight: 700;
      padding: 12px 20px;
      cursor: pointer;
      border-bottom: 3px solid transparent;
      display: flex;
      align-items: center;
      gap: 8px;
      white-space: nowrap;
      transition: all 0.2s;
    }
    .tab-item:hover { color: #fff; }
    .tab-item.active {
      color: var(--accent-bright);
      border-bottom-color: var(--accent-bright);
    }
    .tab-badge {
      background: #1e293b;
      color: #94a3b8;
      font-size: 11px;
      font-family: 'JetBrains Mono', monospace;
      padding: 2px 7px;
      border-radius: 12px;
    }
    .tab-item.active .tab-badge {
      background: rgba(59, 130, 246, 0.25);
      color: var(--accent-bright);
    }

    /* Filter & Search Bar */
    .controls-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 18px;
      gap: 14px;
      flex-wrap: wrap;
    }
    .search-box {
      background: var(--surface);
      border: 1px solid var(--card-border);
      color: #fff;
      padding: 9px 16px;
      border-radius: 8px;
      font-size: 13px;
      width: 320px;
      outline: none;
      transition: all 0.2s;
    }
    .search-box:focus { border-color: var(--accent-bright); }
    .filter-group {
      display: flex;
      gap: 8px;
    }
    .f-pill {
      background: var(--surface);
      border: 1px solid var(--card-border);
      color: var(--text-muted);
      font-size: 12px;
      font-weight: 600;
      padding: 6px 14px;
      border-radius: 20px;
      cursor: pointer;
      transition: all 0.2s;
    }
    .f-pill:hover { background: var(--card-hover); color: #fff; }
    .f-pill.active {
      background: rgba(59, 130, 246, 0.2);
      border-color: var(--accent-bright);
      color: var(--accent-bright);
    }

    /* Modern Table Container */
    .table-card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      overflow-x: auto;
      margin-bottom: 28px;
      box-shadow: 0 4px 20px rgba(0,0,0,0.25);
    }
    table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 13px;
    }
    thead {
      background: #0f1626;
      border-bottom: 1px solid var(--card-border);
    }
    th {
      color: var(--text-muted);
      font-weight: 700;
      text-transform: uppercase;
      font-size: 11px;
      letter-spacing: 0.6px;
      padding: 14px 18px;
      white-space: nowrap;
    }
    td {
      padding: 13px 18px;
      border-bottom: 1px solid #162033;
      font-family: 'JetBrains Mono', monospace;
      color: #e2e8f0;
      white-space: nowrap;
    }
    tr.clickable-row {
      cursor: pointer;
      transition: background 0.15s;
    }
    tr.clickable-row:hover td {
      background-color: rgba(59, 130, 246, 0.08);
    }

    /* Badges */
    .badge {
      display: inline-block;
      padding: 3px 9px;
      border-radius: 6px;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.3px;
    }
    .badge-buy { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }
    .badge-sell { background: rgba(244, 63, 94, 0.15); color: #fb7185; border: 1px solid rgba(244, 63, 94, 0.3); }
    .badge-master { background: rgba(59, 130, 246, 0.2); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.4); }
    .badge-synced { background: rgba(16, 185, 129, 0.2); color: #10b981; }
    .badge-hwm-yes { background: rgba(16, 185, 129, 0.2); color: #10b981; font-weight: 700; }
    .badge-hwm-no { background: rgba(100, 116, 139, 0.2); color: #94a3b8; }
    .badge-shared { background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); font-weight: 700; }
    .badge-type { background: rgba(148, 163, 184, 0.15); color: #cbd5e1; border: 1px solid rgba(148, 163, 184, 0.35); font-size: 11px; padding: 2px 7px; border-radius: 4px; font-weight: 700; }
    .badge-tp { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); font-size: 11px; padding: 2px 7px; border-radius: 4px; font-weight: 700; }
    .badge-sl { background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); font-size: 11px; padding: 2px 7px; border-radius: 4px; font-weight: 700; }
    .badge-mult { background: rgba(168, 85, 247, 0.15); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.35); font-size: 11px; padding: 2px 7px; border-radius: 4px; font-weight: 700; }
    .badge-cat-master { background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.45); font-weight: 800; font-size: 11px; padding: 3px 8px; border-radius: 4px; letter-spacing: 0.3px; }
    .badge-cat-multiplier { background: rgba(168, 85, 247, 0.2); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.45); font-weight: 800; font-size: 11px; padding: 3px 8px; border-radius: 4px; letter-spacing: 0.3px; }
    .badge-cat-equity { background: rgba(59, 130, 246, 0.2); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.45); font-weight: 800; font-size: 11px; padding: 3px 8px; border-radius: 4px; letter-spacing: 0.3px; }
    .badge-cat-balance { background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.45); font-weight: 800; font-size: 11px; padding: 3px 8px; border-radius: 4px; letter-spacing: 0.3px; }
    .btn-view-followers {
      background: rgba(59, 130, 246, 0.2);
      border: 1px solid #3b82f6;
      color: #60a5fa;
      padding: 4px 10px;
      font-size: 11px;
      border-radius: 6px;
      cursor: pointer;
      font-weight: 700;
      transition: all 0.15s;
    }
    .btn-view-followers:hover {
      background: #2563eb;
      color: #fff;
    }
    .btn-view-master {
      background: rgba(168, 85, 247, 0.2);
      border: 1px solid #a855f7;
      color: #c084fc;
      padding: 3px 9px;
      font-size: 11px;
      border-radius: 6px;
      cursor: pointer;
      font-weight: 700;
      transition: all 0.15s;
    }
    .btn-view-master:hover {
      background: #9333ea;
      color: #fff;
    }
    .empty-row {
      text-align: center;
      padding: 48px;
      color: var(--text-dim);
      font-size: 14px;
      font-family: 'Plus Jakarta Sans', sans-serif;
    }

    /* MODAL STYLES (Interactive Follower Order History Drawer) */
    .modal-backdrop {
      display: none;
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(0, 0, 0, 0.75);
      backdrop-filter: blur(4px);
      z-index: 1000;
      align-items: center;
      justify-content: center;
      padding: 20px;
    }
    .modal-window {
      background: #0f1626;
      border: 1px solid var(--card-border);
      border-radius: 16px;
      width: 100%;
      max-width: 1300px;
      max-height: 85vh;
      display: flex;
      flex-direction: column;
      box-shadow: 0 20px 50px rgba(0, 0, 0, 0.5);
      animation: modalFadeIn 0.2s ease-out;
    }
    @keyframes modalFadeIn {
      from { transform: scale(0.96); opacity: 0; }
      to { transform: scale(1); opacity: 1; }
    }
    .modal-header {
      padding: 20px 24px;
      border-bottom: 1px solid var(--card-border);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .modal-header h2 {
      font-size: 18px;
      font-weight: 800;
      color: #fff;
    }
    .modal-header p {
      font-size: 12px;
      color: var(--text-muted);
    }
    .modal-close {
      background: none;
      border: none;
      color: var(--text-muted);
      font-size: 24px;
      cursor: pointer;
      line-height: 1;
    }
    .modal-close:hover { color: #fff; }
    .modal-stats {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      padding: 16px 24px;
      background: #0b101c;
      border-bottom: 1px solid var(--card-border);
    }
    .modal-stat-box {
      font-size: 11px;
      color: var(--text-muted);
      text-transform: uppercase;
    }
    .modal-stat-box div:last-child {
      font-family: 'JetBrains Mono', monospace;
      font-size: 16px;
      font-weight: 700;
      color: #fff;
      margin-top: 2px;
    }
    .modal-body {
      padding: 20px 24px;
      overflow-y: auto;
      flex: 1;
    }

    /* Follower Fleet Manager Controls */
    .fleet-input {
      background: #0b101c;
      border: 1px solid var(--card-border);
      color: #fff;
      font-family: 'JetBrains Mono', monospace;
      padding: 8px 12px;
      border-radius: 8px;
      outline: none;
      transition: all 0.2s;
    }
    .fleet-input:focus { border-color: var(--accent-bright); }
    .fleet-mode-btn {
      background: rgba(15, 23, 42, 0.7);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      color: var(--text-muted);
      padding: 12px 10px;
      cursor: pointer;
      text-align: center;
      transition: all 0.2s;
    }
    .fleet-mode-btn:hover { border-color: rgba(59, 130, 246, 0.5); color: #fff; }
    .fleet-mode-btn.active {
      background: rgba(59, 130, 246, 0.15);
      border-color: var(--accent-bright);
      color: #60a5fa;
      box-shadow: 0 0 12px rgba(59, 130, 246, 0.2);
    }
    .preset-pill {
      background: rgba(30, 41, 59, 0.6);
      border: 1px solid var(--card-border);
      color: var(--text-muted);
      font-size: 11px;
      font-weight: 700;
      padding: 5px 10px;
      border-radius: 6px;
      cursor: pointer;
      transition: all 0.15s;
    }
    .preset-pill:hover { border-color: var(--accent-bright); color: #fff; }
    .preset-pill.active {
      background: rgba(59, 130, 246, 0.25);
      border-color: var(--accent-bright);
      color: #60a5fa;
    }
    .btn-action-primary {
      background: linear-gradient(135deg, #1d4ed8 0%, #2563eb 100%);
      color: #fff;
      border: none;
      box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35);
    }
    .btn-action-primary:hover {
      background: linear-gradient(135deg, #2563eb 0%, #3b82f6 100%);
      transform: translateY(-1px);
    }
    .btn-action-success {
      background: linear-gradient(135deg, #059669 0%, #10b981 100%);
      color: #fff;
      border: none;
      box-shadow: 0 4px 14px rgba(16, 185, 129, 0.35);
    }
    .btn-action-success:hover {
      background: linear-gradient(135deg, #10b981 0%, #34d399 100%);
      transform: translateY(-1px);
    }

    .btn-book-b {
      padding: 3px 8px;
      border-radius: 6px;
      font-size: 11px;
      font-weight: 700;
      border: 1px solid rgba(59, 130, 246, 0.4);
      background: rgba(59, 130, 246, 0.15);
      color: #60a5fa;
      cursor: pointer;
      transition: all 0.2s;
    }
    .btn-book-b:hover {
      background: rgba(59, 130, 246, 0.35);
      box-shadow: 0 0 10px rgba(59, 130, 246, 0.4);
    }
    .btn-book-a {
      padding: 3px 8px;
      border-radius: 6px;
      font-size: 11px;
      font-weight: 700;
      border: 1px solid rgba(245, 158, 11, 0.4);
      background: rgba(245, 158, 11, 0.15);
      color: #fbbf24;
      cursor: pointer;
      transition: all 0.2s;
    }
    .btn-book-a:hover {
      background: rgba(245, 158, 11, 0.35);
      box-shadow: 0 0 10px rgba(245, 158, 11, 0.4);
    }
    .badge-env-real {
      background: rgba(236, 72, 153, 0.2);
      color: #f472b6;
      border: 1px solid rgba(236, 72, 153, 0.4);
      font-weight: 700;
      font-size: 11px;
    }
    .badge-env-paper {
      background: rgba(147, 51, 234, 0.2);
      color: #c084fc;
      border: 1px solid rgba(147, 51, 234, 0.4);
      font-weight: 700;
      font-size: 11px;
    }
    .env-toggle-btn {
      padding: 6px 14px;
      border-radius: 14px;
      font-size: 12px;
      font-weight: 700;
      border: 1px solid var(--card-border);
      background: rgba(15, 23, 42, 0.8);
      color: var(--text-muted);
      cursor: pointer;
      transition: all 0.2s;
    }
    .env-toggle-btn.active {
      background: #3b82f6;
      color: #fff;
      border-color: #3b82f6;
      box-shadow: 0 0 10px rgba(59, 130, 246, 0.5);
    }

  </style>
</head>
<body>

  <!-- Top Header Bar -->
  <div class="top-bar">
    <div class="brand-section">
      <div class="brand-badge">BLACKTRADER</div>
      <div class="title-group">
        <h1>Unified Social Trading Terminal</h1>
        <p>Live Real-Time Monitoring & Profit Share Ledger</p>
      </div>
    </div>

    <!-- Active Master Selector -->
    <div class="master-selector-wrapper">
      <span style="font-size: 11px; text-transform: uppercase; font-weight: 700; color: var(--text-muted);">ACTIVE MASTER:</span>
      <select class="master-select" id="masterSelect" onchange="onMasterChange()">
        <option value="mam" selected>MAM Master (mammaster@mailinator.com - 100 Followers)</option>
      </select>
    </div>

    <div class="top-controls">
      <!-- Active Environment Selector -->
      <div style="display: flex; align-items: center; gap: 6px; background: rgba(15, 23, 42, 0.7); padding: 4px 8px; border-radius: 18px; border: 1px solid var(--card-border);">
        <span style="font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; margin-right: 2px;">ENVIRONMENT:</span>
        <button type="button" id="envBtnPaper" onclick="switchEnvironment('paper')" class="env-toggle-btn active">📄 Paper (Hedging)</button>
        <button type="button" id="envBtnPaperNet" onclick="switchEnvironment('paper-net')" class="env-toggle-btn">📄 Paper (Netting)</button>
        <button type="button" id="envBtnReal" onclick="switchEnvironment('real')" class="env-toggle-btn">💎 Real (Hedging)</button>
        <button type="button" id="envBtnRealNet" onclick="switchEnvironment('real-net')" class="env-toggle-btn">💎 Real (Netting)</button>
      </div>

      <div class="live-status">
        <div class="pulse-dot"></div>
        <span id="liveStatusText">OMS LIVE</span>
      </div>
      <button class="btn" onclick="fetchDashboardData()">⚡ Refresh Now</button>
      <button class="btn active" id="autoSyncBtn" onclick="toggleAutoSync()">Auto-Sync: 3s</button>
    </div>
  </div>

  <!-- SUMMARY CARDS FOR PROFIT SHARED TO MASTER & FOLLOWERS -->
  <div class="kpi-grid">
    <!-- Card 1: Master Balance -->
    <div class="kpi-card">
      <div class="kpi-label">Master Account Balance</div>
      <div class="kpi-val text-cyan" id="kpiMasterBal">$0.00</div>
      <div class="kpi-sub">Equity: <span id="kpiMasterEq">$0.00</span></div>
    </div>

    <!-- Card 2: Total Follower Capital -->
    <div class="kpi-card">
      <div class="kpi-label">Total Follower Capital Pool</div>
      <div class="kpi-val" id="kpiFollowerBal">$0.00</div>
      <div class="kpi-sub"><span id="kpiFollowerCount">100</span> Followers Equity: <span id="kpiFollowerEq">$0.00</span></div>
    </div>

    <!-- Card 3: PROFIT SHARED TO MASTER (NEW CRITICAL SUMMARY CARD) -->
    <div class="kpi-card gold">
      <div class="kpi-label">Total Profit Shared to Master</div>
      <div class="kpi-val text-gold" id="kpiProfitSharedToMaster">$0.00</div>
      <div class="kpi-sub">MAM Manager Share Credited from Followers</div>
    </div>

    <!-- Card 4: PROFIT KEPT BY FOLLOWERS (NEW CRITICAL SUMMARY CARD) -->
    <div class="kpi-card green">
      <div class="kpi-label">Followers Profit Retained (Kept)</div>
      <div class="kpi-val text-green" id="kpiFollowersProfitKept">$0.00</div>
      <div class="kpi-sub"><span id="kpiAboveHwmCount">0</span>/100 Followers Above Benchmark</div>
    </div>

    <!-- Card 5: MASTER TOTAL EARNINGS (TRADING + SHARES) -->
    <div class="kpi-card purple">
      <div class="kpi-label">Master Total Realized Earnings</div>
      <div class="kpi-val text-purple" id="kpiMasterTotalEarnings">$0.00</div>
      <div class="kpi-sub">Trading: <span id="kpiMasterTradePnl">$0.00</span> | Shares: <span id="kpiMasterSharesSub">$0.00</span></div>
    </div>

    <!-- Card 6: REPLICATION SYNC RATE -->
    <div class="kpi-card">
      <div class="kpi-label">Replication Fanout Accuracy</div>
      <div class="kpi-val text-green" id="kpiRepRate">100.0%</div>
      <div class="kpi-sub">Open Trades: <span id="kpiOpenPositions">0</span></div>
    </div>
  </div>

  <!-- Master Info Banner -->
  <div class="master-banner">
    <div class="master-info-left">
      <div class="master-avatar" id="mAvatar">M</div>
      <div>
        <div class="master-email-text" id="mEmail">mammaster@mailinator.com</div>
        <div class="master-sub-text" id="mSubText">MAM Master Account (Member ID: mem_e2dbce29e1c71a7bf6)</div>
      </div>
    </div>
    <div class="master-metrics-right">
      <div>
        <div class="m-stat-title">Unrealized P&L</div>
        <div class="m-stat-val" id="mPnl">$0.00</div>
      </div>
      <div>
        <div class="m-stat-title">Free Margin</div>
        <div class="m-stat-val text-cyan" id="mFreeMargin">$0.00</div>
      </div>
      <div>
        <div class="m-stat-title">Closed Win Rate</div>
        <div class="m-stat-val text-green" id="mWinRate">0.0%</div>
      </div>
      <div>
        <div class="m-stat-title">Last OMS Polled</div>
        <div class="m-stat-val" style="font-size: 14px; color: var(--text-muted);" id="mLastSync">--:--:--</div>
      </div>
    </div>
  </div>

  <!-- SEPARATE DEDICATED TABS -->
  <div class="tabs-bar">
    <button class="tab-item active" onclick="switchTab('master-pos', this)">
      <span>🎯 Master Active Positions</span>
      <span class="tab-badge" id="badgeMasterPos">0</span>
    </button>
    <button class="tab-item" onclick="switchTab('follower-pos', this)">
      <span>⚡ Followers Active Positions</span>
      <span class="tab-badge" id="badgeFollowerPos">0</span>
    </button>
    <button class="tab-item" onclick="switchTab('followers-ledger', this)">
      <span>👥 Follower Accounts & Profit Share Ledger</span>
      <span class="tab-badge" id="badgeFollowers">100</span>
    </button>
    <button class="tab-item" onclick="switchTab('trade-history', this)">
      <span>📜 Master Trade History & Ledger</span>
      <span class="tab-badge" id="badgeHistory">0</span>
    </button>
    <button class="tab-item" onclick="switchTab('fleet-manager', this)">
      <span>⚙️ Follower Fleet Manager</span>
      <span class="tab-badge" style="background: rgba(59, 130, 246, 0.3); color: #60a5fa;" id="badgeFleetManager">100</span>
    </button>
  </div>

  <!-- TAB 1: MASTER ACTIVE POSITIONS (DEDICATED) -->
  <div id="tabContentMasterPos">
    <div class="table-card">
      <table>
        <thead>
          <tr>
            <th>Role</th>
            <th>Master Account</th>
            <th>Market Order ID</th>
            <th>Category</th>
            <th>Symbol</th>
            <th>Type</th>
            <th>Side</th>
            <th>Master Qty</th>
            <th>TP</th>
            <th>SL</th>
            <th>TSL</th>
            <th>Avg Entry Price</th>
            <th>Mark Price</th>
            <th>Unrealized P&L</th>
            <th>Time</th>
            <th>Status</th>
            <th>Followers Copied</th>
          </tr>
        </thead>
        <tbody id="masterPositionsBody">
          <tr><td colspan="17" class="empty-row">No active open positions on Master account. Clean slate.</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- TAB 2: FOLLOWERS ACTIVE POSITIONS (DEDICATED) -->
  <div id="tabContentFollowerPos" style="display: none;">
    <div class="controls-row">
      <input type="text" class="search-box" id="followerPosSearch" placeholder="Filter positions by follower (e.g. mamfollower12)..." onkeyup="renderFollowerPositions()">
      <div style="font-size: 13px; color: var(--text-muted);">Showing <span id="followerPosFilteredCount">0</span> open follower trades</div>
    </div>
    <div class="table-card">
      <table>
        <thead>
          <tr>
            <th>Follower Account</th>
            <th>Order ID</th>
            <th>Master Source</th>
            <th>Category</th>
            <th>Symbol</th>
            <th>Type</th>
            <th>Side</th>
            <th>Follower Qty</th>
            <th>Master Qty</th>
            <th>Multiplier</th>
            <th>TP</th>
            <th>SL</th>
            <th>TSL</th>
            <th>Entry Price</th>
            <th>Current CMP</th>
            <th>Unrealized P&L</th>
            <th>Replication Status</th>
          </tr>
        </thead>
        <tbody id="followerPositionsBody">
          <tr><td colspan="17" class="empty-row">No open replicated follower positions active.</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- TAB 3: FOLLOWER ACCOUNTS, BALANCES & PROFIT SHARES (DEDICATED) -->
  <div id="tabContentFollowersLedger" style="display: none;">
    <div class="controls-row">
      <input type="text" class="search-box" id="followerSearch" placeholder="Search accounts (e.g. mamfollower45)..." onkeyup="renderFollowersLedger()">
      <div class="filter-group">
        <div class="f-pill active" onclick="setFollowerFilter('all', this)">All Accounts (<span id="pillAllCount">100</span>)</div>
        <div class="f-pill" onclick="setFollowerFilter('open', this)">With Open Trades</div>
        <div class="f-pill" onclick="setFollowerFilter('hwm', this)">Above Benchmark (HWM)</div>
      </div>
    </div>
    <div class="table-card">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Follower Account (Click for History)</th>
            <th>Book</th>
            <th>Broker Setting</th>
            <th>Category</th>
            <th>Paper Bal.</th>
            <th>Real Bal.</th>
            <th>Equity</th>
            <th>Benchmark (HWM)</th>
            <th>Above HWM?</th>
            <th>Profit Shared to Master</th>
            <th>Profit Kept</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody id="followersLedgerBody">
          <tr><td colspan="12" class="empty-row">Loading follower ledger...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- TAB 4: CLOSED TRADE HISTORY & LEDGER (DEDICATED) -->
  <div id="tabContentTradeHistory" style="display: none;">
    <div class="controls-row">
      <input type="text" class="search-box" id="historySearch" placeholder="Filter history by symbol or order ID..." onkeyup="renderHistoryTable()">
      <div style="font-size: 13px; color: var(--text-muted);">
        Total Closed Trades: <strong id="histTotalCount">0</strong> | Total Realized P&L: <strong id="histTotalPnl">$0.00</strong>
      </div>
    </div>
    <div class="table-card">
      <table>
        <thead>
          <tr>
            <th>History ID</th>
            <th>Executed Time</th>
            <th>Category</th>
            <th>Symbol</th>
            <th>Type</th>
            <th>Side</th>
            <th>Master Qty</th>
            <th>TP</th>
            <th>SL</th>
            <th>TSL</th>
            <th>Entry Price</th>
            <th>Exit Price</th>
            <th>Realized P&L</th>
            <th>Exit Source</th>
            <th>Attribution</th>
            <th>Followers Copied</th>
          </tr>
        </thead>
        <tbody id="historyTableBody">
          <tr><td colspan="16" class="empty-row">No trade history recorded yet.</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- INTERACTIVE MODAL: FOLLOWER ORDER HISTORY & PROFIT SHARE BREAKDOWN -->
  <div class="modal-backdrop" id="followerModal" onclick="closeModalOnBackdrop(event)">
    <div class="modal-window">
      <div class="modal-header">
        <div>
          <h2 id="modalFollowerEmail">mamfollower1@mailinator.com</h2>
          <p id="modalFollowerSub">Follower Profile & Copied Orders Profit Share Ledger</p>
        </div>
        <button class="modal-close" onclick="closeFollowerModal()">&times;</button>
      </div>

      <div class="modal-stats">
        <div class="modal-stat-box">
          <div>Following Manager</div>
          <div id="modalMgrName">mammaster (50%)</div>
        </div>
        <div class="modal-stat-box">
          <div>Starting Benchmark (HWM)</div>
          <div id="modalBenchmark">$9,988,415.07</div>
        </div>
        <div class="modal-stat-box">
          <div>Current Balance</div>
          <div id="modalBalance">$9,988,415.07</div>
        </div>
        <div class="modal-stat-box">
          <div>Total Profit Shared to Master</div>
          <div class="text-gold" id="modalSharedTotal">$0.00</div>
        </div>
        <div class="modal-stat-box">
          <div>Total Profit Kept</div>
          <div class="text-green" id="modalKeptTotal">$0.00</div>
        </div>
      </div>

      <div class="modal-body">
        <div style="font-weight: 700; font-size: 14px; margin-bottom: 12px; color: #fff;">
          Copied Orders Profit Share Breakdown (High-Water Mark Rule: 50% only when Balance > Benchmark)
        </div>
        <div class="table-card" style="margin-bottom: 0;">
          <table>
            <thead>
              <tr>
                <th>Trade ID</th>
                <th>Executed At</th>
                <th>Category</th>
                <th>Symbol</th>
                <th>Type</th>
                <th>Side</th>
                <th>Follower Qty</th>
                <th>Master Qty</th>
                <th>TP</th>
                <th>SL</th>
                <th>TSL</th>
                <th>Trade Gross P&L</th>
                <th>Balance Before</th>
                <th>Above Benchmark?</th>
                <th>Manager Share (50%)</th>
                <th>Follower Kept</th>
              </tr>
            </thead>
            <tbody id="modalSharesTableBody">
              <tr><td colspan="16" class="empty-row">No trade shares recorded for this follower yet.</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>

  <!-- MODAL 2: MASTER ACTIVE ORDER DETAILS & REPLICATED FOLLOWERS -->
  <div class="modal-backdrop" id="masterPosFollowersModal" onclick="closeModalOnBackdrop(event)">
    <div class="modal-window" style="max-width: 1350px;">
      <div class="modal-header">
        <div>
          <h2 id="mPosModalTitle">🎯 Master Active Order & Replicated Follower Orders</h2>
          <p id="mPosModalSub">Live replication status, lot multiplier validation, and follower execution details</p>
        </div>
        <button class="modal-close" onclick="closeModal('masterPosFollowersModal')">&times;</button>
      </div>

      <div class="modal-stats" id="mPosModalStats">
      </div>

      <div class="modal-body">
        <div style="font-weight: 700; font-size: 14px; margin-bottom: 12px; color: #fff; display: flex; justify-content: space-between;">
          <span>Replicated Follower Positions (<span id="mPosFollowerCount">0</span> Accounts Copied)</span>
          <span style="color: var(--text-muted); font-size: 12px;">Sync Accuracy: <strong style="color: #34d399;">100.0%</strong></span>
        </div>
        <div class="table-card" style="margin-bottom: 0;">
          <table>
            <thead>
              <tr>
                <th>Follower Account</th>
                <th>Follower Order ID</th>
                <th>Category</th>
                <th>Symbol</th>
                <th>Type</th>
                <th>Side</th>
                <th>Follower Qty</th>
                <th>Master Qty</th>
                <th>Multiplier</th>
                <th>TP</th>
                <th>SL</th>
                <th>TSL</th>
                <th>Entry Price</th>
                <th>Mark Price</th>
                <th>Unrealized P&L</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody id="mPosFollowersTableBody">
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>

  <!-- MODAL 3: FOLLOWER TO MASTER SOURCE ORDER MODAL -->
  <div class="modal-backdrop" id="followerToMasterModal" onclick="closeModalOnBackdrop(event)">
    <div class="modal-window" style="max-width: 1000px;">
      <div class="modal-header">
        <div>
          <h2 id="fToMTitle">🎯 Originating Master Trade Details</h2>
          <p id="fToMSub">Showing the Master order that this follower trade was copied from</p>
        </div>
        <button class="modal-close" onclick="closeModal('followerToMasterModal')">&times;</button>
      </div>

      <div class="modal-stats" id="fToMStats">
      </div>

      <div class="modal-body" id="fToMBody">
      </div>
    </div>
  </div>

  <!-- MODAL 4: MASTER CLOSED TRADE & REPLICATED FOLLOWERS HISTORY -->
  <div class="modal-backdrop" id="masterHistFollowersModal" onclick="closeModalOnBackdrop(event)">
    <div class="modal-window" style="max-width: 1350px;">
      <div class="modal-header">
        <div>
          <h2 id="mHistModalTitle">📜 Master Closed Trade & Followers Execution Ledger</h2>
          <p id="mHistModalSub">Auditing follower copied trades, realized P&L, and profit shares for this specific Master execution</p>
        </div>
        <button class="modal-close" onclick="closeModal('masterHistFollowersModal')">&times;</button>
      </div>

      <div class="modal-stats" id="mHistModalStats">
      </div>

      <div class="modal-body">
        <div style="font-weight: 700; font-size: 14px; margin-bottom: 12px; color: #fff;">
          All Followers Copied Closed Orders (<span id="mHistFollowerCount">0</span> Accounts Copied)
        </div>
        <div class="table-card" style="margin-bottom: 0;">
          <table>
            <thead>
              <tr>
                <th>Follower Account</th>
                <th>Follower Trade ID</th>
                <th>Category</th>
                <th>Symbol</th>
                <th>Type</th>
                <th>Side</th>
                <th>Follower Qty</th>
                <th>Master Qty</th>
                <th>TP</th>
                <th>SL</th>
                <th>TSL</th>
                <th>Entry Price</th>
                <th>Exit Price</th>
                <th>Follower Gross P&L</th>
                <th>Above HWM?</th>
                <th>Manager Share (50%)</th>
                <th>Follower Kept</th>
              </tr>
            </thead>
            <tbody id="mHistFollowersTableBody">
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>

  <!-- TAB 5: FOLLOWER FLEET MANAGER (DEDICATED) -->
  <div id="tabContentFleetManager" style="display: none;">
    <div style="margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; background: rgba(30, 41, 59, 0.4); padding: 16px 20px; border-radius: 12px; border: 1px solid var(--card-border);">
      <div>
        <h2 style="font-size: 18px; font-weight: 800; color: #fff; margin-bottom: 4px;">⚙️ Follower Fleet Control Center</h2>
        <p style="font-size: 13px; color: var(--text-muted);">Dynamically configure Master MAM Profit Share, Follower Sizing Modes & Multipliers, and inject capital balances via Admin API</p>
      </div>
      <div style="display: flex; gap: 10px;">
        <span class="badge" style="background: rgba(16, 185, 129, 0.15); color: #34d399; font-size: 12px; padding: 6px 14px;">100 Followers Active</span>
        <span class="badge" style="background: rgba(59, 130, 246, 0.15); color: #60a5fa; font-size: 12px; padding: 6px 14px;">Master: mem_e2dbce29e1c71a7bf6</span>
      </div>
    </div>

    <!-- MASTER MAM SETTINGS CARD: PROFIT SHARE (DECIDED EXCLUSIVELY BY MASTER) -->
    <div class="kpi-card" style="padding: 24px; margin-bottom: 24px; border: 1px solid rgba(168, 85, 247, 0.4); background: linear-gradient(135deg, rgba(15, 23, 42, 0.95) 0%, rgba(30, 27, 75, 0.4) 100%);">
      <div style="display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 1px solid var(--card-border); padding-bottom: 14px; margin-bottom: 18px;">
        <div>
          <div style="font-weight: 800; font-size: 17px; color: #c084fc; display: flex; align-items: center; gap: 8px;">
            <span>👑 MAM Master Profit Share & Profile Settings</span>
            <span class="badge" style="background: rgba(168, 85, 247, 0.2); color: #d8b4fe; font-size: 11px;">FLOW: MASTER ID &rarr; MAM &rarr; SETTINGS &rarr; SAVE</span>
          </div>
          <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">
            Profit share is determined <strong>exclusively by the MAM Master</strong>. Followers cannot choose this share; they join knowing this established manager rate.
          </div>
        </div>
        <div style="text-align: right;">
          <span class="badge badge-gold" id="currentMasterShareBadge" style="font-size: 13px; padding: 6px 14px;">MY SHARE: 50%</span>
        </div>
      </div>

      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 24px; align-items: center;">
        <div style="display: flex; flex-direction: column; gap: 14px;">
          <div>
            <label style="font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">Shown to Followers as (Display Name)</label>
            <input type="text" id="masterDisplayNameInput" value="mammaster" class="fleet-input" style="width: 100%; margin-top: 6px; font-weight: 700;">
          </div>
          <div>
            <label style="font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">My Share (%)</label>
            <div style="display: flex; gap: 12px; align-items: center; margin-top: 6px;">
              <div style="position: relative; width: 120px;">
                <input type="number" id="masterShareInput" value="50" min="0" max="100" class="fleet-input" style="width: 100%; font-size: 16px; font-weight: 800; color: #fbbf24; text-align: center;">
              </div>
              <div style="display: flex; gap: 6px; flex-wrap: wrap;" id="masterSharePresets">
                <button type="button" class="preset-pill" onclick="setMasterPresetShare(20)">20%</button>
                <button type="button" class="preset-pill" onclick="setMasterPresetShare(30)">30%</button>
                <button type="button" class="preset-pill" onclick="setMasterPresetShare(40)">40%</button>
                <button type="button" class="preset-pill active" onclick="setMasterPresetShare(50)">50%</button>
                <button type="button" class="preset-pill" onclick="setMasterPresetShare(60)">60%</button>
              </div>
            </div>
          </div>
        </div>

        <div style="display: flex; flex-direction: column; gap: 12px;">
          <div style="background: rgba(0,0,0,0.35); border: 1px solid rgba(168, 85, 247, 0.25); border-radius: 8px; padding: 12px 16px; font-size: 12px; line-height: 1.5; color: #cbd5e1;">
            <div style="font-weight: 700; color: #facc15; margin-bottom: 2px;">⚠️ High-Water Mark Benchmark Rule</div>
            Changing your share affects followers who join after the change &mdash; existing followers keep the share they agreed to.
          </div>
          <button class="btn" id="btnSaveMasterShare" onclick="saveMasterMAMSettings()" style="background: linear-gradient(135deg, #7e22ce 0%, #a855f7 100%); color: #fff; border: none; font-weight: 700; font-size: 14px; padding: 12px 20px; justify-content: center; box-shadow: 0 4px 15px rgba(168, 85, 247, 0.3);">
            💾 Save Master Profit Share to MAM Settings
          </button>
          <div id="masterShareStatusBox" style="display: none; padding: 10px 14px; border-radius: 8px; font-size: 12px; background: rgba(30, 41, 59, 0.6); border: 1px solid var(--card-border);">
          </div>
        </div>
      </div>
    </div>

        <!-- 4-CARD FLEET MANAGEMENT CONTROLLERS GRID -->
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 24px;">

      <!-- CARD 1: MAM CATEGORY & MULTIPLIER CONTROLLER -->
      <div class="kpi-card" style="padding: 24px; display: flex; flex-direction: column; gap: 18px; border: 1px solid rgba(59, 130, 246, 0.3); background: rgba(15, 23, 42, 0.85);">
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--card-border); padding-bottom: 12px;">
          <div>
            <div style="font-weight: 800; font-size: 16px; color: #60a5fa; display: flex; align-items: center; gap: 8px;">
              <span>🎛️ Follower MAM Category & Sizing Controller</span>
            </div>
            <div style="font-size: 12px; color: var(--text-muted); margin-top: 2px;">Switch replication sizing mode across follower accounts</div>
          </div>
          <span class="badge badge-mult" id="catActiveBadge">MULTIPLIER (2.0x)</span>
        </div>

        <!-- Target Scope -->
        <div>
          <label style="font-size: 12px; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">1. Target Followers Scope</label>
          <div style="display: flex; gap: 16px; margin-top: 8px;">
            <label style="display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 13px; color: #cbd5e1;">
              <input type="radio" name="catScope" value="all" checked onchange="onCatScopeChange()"> All 100 Followers
            </label>
            <label style="display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 13px; color: #cbd5e1;">
              <input type="radio" name="catScope" value="range" onchange="onCatScopeChange()"> Index Range
            </label>
            <label style="display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 13px; color: #cbd5e1;">
              <input type="radio" name="catScope" value="single" onchange="onCatScopeChange()"> Single Account
            </label>
          </div>

          <div id="catRangeRow" style="display: none; gap: 10px; margin-top: 10px; align-items: center;">
            <span style="font-size: 12px; color: var(--text-muted);">From:</span>
            <input type="number" id="catStartIdx" value="1" min="1" max="100" class="fleet-input" style="width: 70px;">
            <span style="font-size: 12px; color: var(--text-muted);">To:</span>
            <input type="number" id="catEndIdx" value="100" min="1" max="100" class="fleet-input" style="width: 70px;">
            <span style="font-size: 11px; color: var(--text-dim);">(mamfollower1 .. mamfollower100)</span>
          </div>

          <div id="catSingleRow" style="display: none; margin-top: 10px;">
            <select id="catSingleSelect" class="fleet-input" style="width: 100%;"></select>
          </div>
        </div>

        <!-- Category Mode Selection -->
        <div>
          <label style="font-size: 12px; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">2. Sizing Category Mode</label>
          <div style="display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 10px; margin-top: 8px;">
            <button type="button" class="fleet-mode-btn active" id="btnModeMult" onclick="selectFleetCategory('multiplier')">
              <div style="font-weight: 700;">Multiplier</div>
              <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">Fixed Lot Ratio</div>
            </button>
            <button type="button" class="fleet-mode-btn" id="btnModeEq" onclick="selectFleetCategory('equity')">
              <div style="font-weight: 700;">Equity Based</div>
              <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">Follower/Master Eq</div>
            </button>
            <button type="button" class="fleet-mode-btn" id="btnModeBal" onclick="selectFleetCategory('balance')">
              <div style="font-weight: 700;">Balance Based</div>
              <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">Follower/Master Bal</div>
            </button>
            <button type="button" class="fleet-mode-btn" id="btnModeLeave" onclick="selectFleetCategory('leave')" style="border-color: rgba(239, 68, 68, 0.4);">
              <div style="font-weight: 700; color: #f87171;">🚪 Leave Master</div>
              <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">Unfollow from MAM</div>
            </button>
          </div>
        </div>

        <!-- Multiplier Value & Presets -->
        <div id="multiplierSection">
          <label style="font-size: 12px; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">3. Multiplier Factor</label>
          <div style="display: flex; gap: 12px; align-items: center; margin-top: 8px;">
            <input type="number" id="fleetMultiplierInput" value="2.0" step="0.1" min="0.1" max="10.0" class="fleet-input" style="width: 110px; font-size: 15px; font-weight: 700;">
            <div style="display: flex; gap: 6px; flex-wrap: wrap;">
              <button type="button" class="preset-pill" onclick="setPresetMult(1.0)">1.0x</button>
              <button type="button" class="preset-pill" onclick="setPresetMult(1.5)">1.5x</button>
              <button type="button" class="preset-pill active" id="pillMult2" onclick="setPresetMult(2.0)">2.0x</button>
              <button type="button" class="preset-pill" onclick="setPresetMult(2.5)">2.5x</button>
              <button type="button" class="preset-pill" onclick="setPresetMult(3.0)">3.0x</button>
              <button type="button" class="preset-pill" onclick="setPresetMult(5.0)">5.0x</button>
            </div>
          </div>
        </div>

        <!-- Manager Profit Share Banner (Inherited) -->
        <div style="display: flex; justify-content: space-between; align-items: center; background: rgba(0,0,0,0.3); padding: 12px 14px; border-radius: 8px; border: 1px dashed rgba(251, 191, 36, 0.3);">
          <div>
            <div style="font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">Manager Profit Share (Inherited from Master)</div>
            <div style="font-size: 11px; color: var(--text-dim); margin-top: 2px;">Decided solely by MAM Master. Followers follow under this rate.</div>
          </div>
          <span class="badge badge-gold" id="followerInheritedShare" style="font-weight: 800; font-size: 13px;">50% (HWM)</span>
        </div>

        <div id="leaveMasterNotice" style="display: none; background: rgba(239, 68, 68, 0.1); padding: 12px 14px; border-radius: 8px; font-size: 12px; color: #fca5a5; border: 1px dashed rgba(239, 68, 68, 0.4);">
          ⚠️ <strong>Leave Master Mode Selected</strong>: All targeted followers will cleanly unfollow from the MAM master across all instances. Replication will cease immediately.
        </div>

        <!-- Action Buttons -->
        <div style="display: flex; gap: 10px; flex-wrap: wrap;">
          <button class="btn btn-action-primary" id="btnApplyCat" onclick="applyFleetCategory()" style="flex: 2; min-width: 200px; padding: 12px 16px; font-size: 14px; font-weight: 700; justify-content: center;">
            🚀 Apply Category Configuration
          </button>
          <button class="btn" id="btnBulkFollow" onclick="applyFleetBulkFollow()" style="flex: 2; min-width: 200px; padding: 12px 16px; font-size: 14px; font-weight: 700; justify-content: center; background: linear-gradient(135deg, #2563eb 0%, #3b82f6 100%); color: #fff; border: none; border-radius: 8px; cursor: pointer;">
            👥 Bulk Follow Master (Default Equity)
          </button>
          <button class="btn" id="btnApplyUnfollow" onclick="applyFleetUnfollow()" style="flex: 1; min-width: 130px; padding: 12px 16px; font-size: 14px; font-weight: 700; justify-content: center; background: linear-gradient(135deg, #dc2626 0%, #ef4444 100%); color: #fff; border: none; border-radius: 8px; cursor: pointer;">
            🚪 Leave Master
          </button>
        </div>

        <div id="catStatusBox" style="display: none; padding: 12px; border-radius: 8px; font-size: 12px; background: rgba(30, 41, 59, 0.5); border: 1px solid var(--card-border);"></div>
      </div>

      <!-- CARD 2: BROKER SETTINGS CONTROLLER (TRADES MODULE SETTINGS) -->
      <div class="kpi-card" style="padding: 24px; display: flex; flex-direction: column; gap: 18px; border: 1px solid rgba(139, 92, 246, 0.4); background: rgba(15, 23, 42, 0.9);">
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--card-border); padding-bottom: 12px;">
          <div>
            <div style="font-weight: 800; font-size: 16px; color: #a78bfa; display: flex; align-items: center; gap: 8px;">
              <span>⚙️ Followers Broker Setting Controller</span>
            </div>
            <div style="font-size: 12px; color: var(--text-muted); margin-top: 2px;">Enable or disable broker settings (Hedging / Netting) across followers (matching Trades &rarr; Settings)</div>
          </div>
          <span class="badge badge-env-real" id="brokerActiveBadge">REAL (HEDGING) ● CONNECTED</span>
        </div>

        <!-- 1. Target Scope -->
        <div>
          <label style="font-size: 12px; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">1. Target Followers Scope</label>
          <div style="display: flex; gap: 16px; margin-top: 8px;">
            <label style="display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 13px; color: #cbd5e1;">
              <input type="radio" name="brokerScope" value="all" checked onchange="onBrokerScopeChange()"> All 100 Followers
            </label>
            <label style="display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 13px; color: #cbd5e1;">
              <input type="radio" name="brokerScope" value="range" onchange="onBrokerScopeChange()"> Index Range
            </label>
            <label style="display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 13px; color: #cbd5e1;">
              <input type="radio" name="brokerScope" value="single" onchange="onBrokerScopeChange()"> Single Account
            </label>
          </div>

          <div id="brokerRangeRow" style="display: none; gap: 10px; margin-top: 10px; align-items: center;">
            <span style="font-size: 12px; color: var(--text-muted);">From:</span>
            <input type="number" id="brokerStartIdx" value="1" min="1" max="100" class="fleet-input" style="width: 70px;">
            <span style="font-size: 12px; color: var(--text-muted);">To:</span>
            <input type="number" id="brokerEndIdx" value="100" min="1" max="100" class="fleet-input" style="width: 70px;">
          </div>
          <div id="brokerSingleRow" style="display: none; margin-top: 10px;">
            <select id="brokerSingleSelect" class="fleet-input" style="width: 100%;"></select>
          </div>
        </div>

        <!-- 2. Trades Settings Modal Replication -->
        <div style="background: #0f172a; border: 1px solid #1e293b; border-radius: 10px; overflow: hidden;">
          <!-- Broker Tabs -->
          <div style="display: flex; border-bottom: 1px solid #1e293b; background: rgba(15, 23, 42, 0.6); overflow-x: auto;">
            <button type="button" class="broker-tab-btn" id="tabBrokerPaper" onclick="selectFleetBrokerTab('paper')" style="padding: 10px 16px; font-size: 13px; font-weight: 600; color: #94a3b8; background: none; border: none; border-bottom: 2px solid transparent; cursor: pointer; display: flex; align-items: center; gap: 6px;">
              Paper (Hedging) <span id="dotBrokerPaper" style="width: 6px; height: 6px; border-radius: 50%; background: #10b981;"></span>
            </button>
            <button type="button" class="broker-tab-btn active" id="tabBrokerReal" onclick="selectFleetBrokerTab('real')" style="padding: 10px 16px; font-size: 13px; font-weight: 700; color: #60a5fa; background: none; border: none; border-bottom: 2px solid #3b82f6; cursor: pointer; display: flex; align-items: center; gap: 6px;">
              Real (Hedging) <span id="dotBrokerReal" style="width: 6px; height: 6px; border-radius: 50%; background: #10b981;"></span>
            </button>
            <button type="button" class="broker-tab-btn" id="tabBrokerPaperNet" onclick="selectFleetBrokerTab('paper-net')" style="padding: 10px 16px; font-size: 13px; font-weight: 600; color: #94a3b8; background: none; border: none; border-bottom: 2px solid transparent; cursor: pointer; display: flex; align-items: center; gap: 6px;">
              Paper (Netting) <span id="dotBrokerPaperNet" style="width: 6px; height: 6px; border-radius: 50%; background: #64748b;"></span>
            </button>
            <button type="button" class="broker-tab-btn" id="tabBrokerRealNet" onclick="selectFleetBrokerTab('real-net')" style="padding: 10px 16px; font-size: 13px; font-weight: 600; color: #94a3b8; background: none; border: none; border-bottom: 2px solid transparent; cursor: pointer; display: flex; align-items: center; gap: 6px;">
              Real (Netting) <span id="dotBrokerRealNet" style="width: 6px; height: 6px; border-radius: 50%; background: #10b981;"></span>
            </button>
          </div>

          <!-- Active Broker Tab Body -->
          <div style="padding: 16px; display: flex; flex-direction: column; gap: 14px;">
            <div style="display: flex; align-items: center; gap: 8px; font-size: 13px; color: #94a3b8;">
              <span>Broker ID:</span>
              <strong id="brokerIdLabel" style="color: #f1f5f9; font-family: monospace;">real</strong>
              <button type="button" onclick="navigator.clipboard.writeText(document.getElementById('brokerIdLabel').innerText)" style="background: none; border: none; color: #a78bfa; font-size: 12px; cursor: pointer;">📋 Copy</button>
            </div>

            <!-- Enable Checkbox Container (Identical to Trades Settings) -->
            <div style="background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 14px 18px; display: flex; justify-content: space-between; align-items: center;">
              <label style="display: flex; align-items: center; gap: 12px; cursor: pointer; margin: 0;">
                <input type="checkbox" id="chkEnableBroker" checked onchange="onBrokerCheckboxToggle()" style="width: 18px; height: 18px; accent-color: #8b5cf6; cursor: pointer;">
                <span id="lblEnableBroker" style="font-size: 15px; font-weight: 700; color: #ffffff;">Enable Real (Hedging)</span>
              </label>
              <div id="brokerConnectedIndicator" style="display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 600; color: #10b981;">
                <span id="brokerConnectedDot" style="width: 8px; height: 8px; border-radius: 50%; background: #10b981; display: inline-block;"></span> <span id="brokerConnectedText">connected</span>
              </div>
            </div>

            <!-- Balance Box (Identical to Trades Settings) -->
            <div style="background: #111827; border: 1px solid #1f2937; border-radius: 8px; padding: 14px 16px;">
              <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 10px;">
                <span style="font-size: 14px; font-weight: 700; color: #ffffff;">Balance</span>
                <span id="brokerMoneyTag" class="badge" style="background: rgba(245, 158, 11, 0.2); color: #f59e0b; font-size: 10px; font-weight: 800; padding: 2px 8px; border-radius: 4px;">REAL MONEY</span>
              </div>
              <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; text-align: left;">
                <div>
                  <div style="font-size: 10px; font-weight: 700; color: #64748b; text-transform: uppercase;">BALANCE</div>
                  <div id="brokerBalVal" style="font-size: 14px; font-weight: 800; color: #f1f5f9; margin-top: 2px;">1,000.00</div>
                </div>
                <div>
                  <div style="font-size: 10px; font-weight: 700; color: #64748b; text-transform: uppercase;">EQUITY</div>
                  <div id="brokerEqVal" style="font-size: 14px; font-weight: 800; color: #f1f5f9; margin-top: 2px;">1,000.00</div>
                </div>
                <div>
                  <div style="font-size: 10px; font-weight: 700; color: #64748b; text-transform: uppercase;">FREE MARGIN</div>
                  <div id="brokerFreeVal" style="font-size: 14px; font-weight: 800; color: #f1f5f9; margin-top: 2px;">1,000.00</div>
                </div>
                <div>
                  <div style="font-size: 10px; font-weight: 700; color: #64748b; text-transform: uppercase;">USED MARGIN</div>
                  <div id="brokerUsedVal" style="font-size: 14px; font-weight: 800; color: #f1f5f9; margin-top: 2px;">0.00</div>
                </div>
              </div>
              <div id="brokerBalanceDesc" style="font-size: 11px; color: #94a3b8; margin-top: 10px;">
                This is a real-money account. Its balance changes by deposit or an admin adjustment.
              </div>
            </div>
          </div>
        </div>

        <!-- 3. Fleet Action Buttons -->
        <div style="display: flex; gap: 12px;">
          <button class="btn" id="btnEnableBrokerFleet" onclick="applyFleetBrokerToggle('enable')" style="flex: 1; background: linear-gradient(135deg, #059669 0%, #10b981 100%); color: #fff; padding: 12px 16px; font-size: 14px; font-weight: 700; justify-content: center; border: none; border-radius: 8px; cursor: pointer;">
            🟢 Enable Broker Setting for Followers
          </button>
          <button class="btn" id="btnDisableBrokerFleet" onclick="applyFleetBrokerToggle('disable')" style="flex: 1; background: linear-gradient(135deg, #dc2626 0%, #ef4444 100%); color: #fff; padding: 12px 16px; font-size: 14px; font-weight: 700; justify-content: center; border: none; border-radius: 8px; cursor: pointer;">
            🔴 Disable Broker Setting for Followers
          </button>
        </div>

        <!-- Chrome Live Browser Sync Helper -->
        <div style="background: rgba(59, 130, 246, 0.08); border: 1px dashed rgba(59, 130, 246, 0.35); border-radius: 8px; padding: 12px 14px; font-size: 12px; color: #93c5fd;">
          💡 <strong>Chrome Terminal Sync Tip</strong>: The BlackTrader trading UI stores the Trades &rarr; Settings checkbox in browser <code>localStorage</code>. When you log in as a follower in Chrome, you can paste this 1-line command into Chrome Console (F12) to instantly tick the selected broker checkbox:
          <div style="display: flex; gap: 8px; margin-top: 8px; align-items: center;">
            <code id="chromeSyncSnippet" style="background: rgba(0,0,0,0.6); padding: 6px 10px; border-radius: 4px; color: #38bdf8; font-size: 11px; flex: 1; overflow-x: auto; font-family: monospace;">const f = document.querySelector('iframe'); const uid = f ? f.contentWindow.__IFRAME_CONFIG__?.user_id : ''; if(f && uid) { f.contentWindow.localStorage.setItem('selectedBrokers:' + uid, JSON.stringify(['real'])); f.contentWindow.location.reload(); }</code>
            <button type="button" class="btn" onclick="copyChromeSyncSnippet()" style="padding: 6px 12px; font-size: 11px; background: #3b82f6; color: white; border: none; white-space: nowrap; cursor: pointer;">📋 Copy Snippet</button>
          </div>
        </div>

        <div id="brokerStatusBox" style="display: none; padding: 12px; border-radius: 8px; font-size: 12px; background: rgba(30, 41, 59, 0.5); border: 1px solid var(--card-border);"></div>
      </div>

      <!-- CARD 3: CAPITAL & BALANCE CONTROLLER (ADMIN API) -->
      <div class="kpi-card" style="padding: 24px; display: flex; flex-direction: column; gap: 18px; border: 1px solid rgba(16, 185, 129, 0.3); background: rgba(15, 23, 42, 0.85);">
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--card-border); padding-bottom: 12px;">
          <div>
            <div style="font-weight: 800; font-size: 16px; color: #34d399; display: flex; align-items: center; gap: 8px;">
              <span>💰 Capital & Balance Controller (Admin API)</span>
            </div>
            <div style="font-size: 12px; color: var(--text-muted); margin-top: 2px;">Set live capital balance for Paper and Real accounts</div>
          </div>
          <span class="badge badge-synced">ADMIN API</span>
        </div>

        <!-- Target Scope -->
        <div>
          <label style="font-size: 12px; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">1. Target Scope</label>
          <div style="display: flex; gap: 16px; margin-top: 8px; flex-wrap: wrap;">
            <label style="display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 13px; color: #cbd5e1;">
              <input type="radio" name="balScope" value="all" checked onchange="onBalScopeChange()"> All 100 Followers
            </label>
            <label style="display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 13px; color: #cbd5e1;">
              <input type="radio" name="balScope" value="range" onchange="onBalScopeChange()"> Index Range
            </label>
            <label style="display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 13px; color: #cbd5e1;">
              <input type="radio" name="balScope" value="single" onchange="onBalScopeChange()"> Single Account
            </label>
            <label style="display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 13px; color: #fbbf24;">
              <input type="radio" name="balScope" value="master" onchange="onBalScopeChange()"> 👑 Master Account
            </label>
          </div>

          <div id="balRangeRow" style="display: none; gap: 10px; margin-top: 10px; align-items: center;">
            <span style="font-size: 12px; color: var(--text-muted);">From:</span>
            <input type="number" id="balStartIdx" value="1" min="1" max="100" class="fleet-input" style="width: 70px;">
            <span style="font-size: 12px; color: var(--text-muted);">To:</span>
            <input type="number" id="balEndIdx" value="100" min="1" max="100" class="fleet-input" style="width: 70px;">
          </div>
          <div id="balSingleRow" style="display: none; margin-top: 10px;">
            <select id="balSingleSelect" class="fleet-input" style="width: 100%;"></select>
          </div>
        </div>

        <!-- Target Environment -->
        <div>
          <label style="font-size: 12px; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">2. Target Environment</label>
          <div style="display: flex; gap: 8px; margin-top: 8px;">
            <button type="button" class="preset-pill active" id="balEnvPaper" onclick="selectBalEnv('paper')">📄 Paper (Hedging)</button>
            <button type="button" class="preset-pill" id="balEnvReal" onclick="selectBalEnv('real')">💎 Real (Hedging)</button>
            <button type="button" class="preset-pill" id="balEnvRealNet" onclick="selectBalEnv('real-net')">🔷 Real (Netting)</button>
            <button type="button" class="preset-pill" id="balEnvBoth" onclick="selectBalEnv('both')">🌐 Both (Paper & Real)</button>
          </div>
        </div>

        <!-- Target Balance Input & Presets -->
        <div>
          <label style="font-size: 12px; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">3. Target Capital Balance ($)</label>
          <div style="display: flex; gap: 12px; align-items: center; margin-top: 8px;">
            <div style="position: relative; width: 180px;">
              <span style="position: absolute; left: 12px; top: 9px; color: #34d399; font-weight: 700;">$</span>
              <input type="number" id="fleetBalanceInput" value="10000000" step="100000" class="fleet-input" style="width: 100%; padding-left: 26px; font-size: 15px; font-weight: 700;">
            </div>
            <div style="display: flex; gap: 6px; flex-wrap: wrap;">
              <button type="button" class="preset-pill" onclick="setPresetBal(1000000)">$1M</button>
              <button type="button" class="preset-pill" onclick="setPresetBal(5000000)">$5M</button>
              <button type="button" class="preset-pill active" id="pillBal10m" onclick="setPresetBal(10000000)">$10M</button>
              <button type="button" class="preset-pill" onclick="setPresetBal(25000000)">$25M</button>
              <button type="button" class="preset-pill" onclick="setPresetBal(100000000)">$100M</button>
            </div>
          </div>
        </div>

        <!-- Action Button -->
        <button class="btn btn-action-success" id="btnApplyBal" onclick="applyFleetBalance()" style="padding: 12px 20px; font-size: 14px; font-weight: 700; width: 100%; justify-content: center; background: linear-gradient(135deg, #059669 0%, #10b981 100%); border-radius: 8px;">
          💸 Set Account Balances via Admin API
        </button>

        <div id="balStatusBox" style="display: none; padding: 12px; border-radius: 8px; font-size: 12px; background: rgba(30, 41, 59, 0.5); border: 1px solid var(--card-border);"></div>
      </div>

      <!-- CARD 4: BOOK CONVERSION CONTROLLER (ADMIN API) -->
      <div class="kpi-card" style="padding: 24px; display: flex; flex-direction: column; gap: 18px; border: 1px solid rgba(245, 158, 11, 0.3); background: rgba(15, 23, 42, 0.85);">
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--card-border); padding-bottom: 12px;">
          <div>
            <div style="font-weight: 800; font-size: 16px; color: #fbbf24; display: flex; align-items: center; gap: 8px;">
              <span>📖 Book Conversion Controller (Admin API)</span>
            </div>
            <div style="font-size: 12px; color: var(--text-muted); margin-top: 2px;">Convert followers between B-Book and A-Book</div>
          </div>
          <span class="badge badge-gold">ADMIN API</span>
        </div>

        <!-- Target Scope -->
        <div>
          <label style="font-size: 12px; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">1. Target Followers Scope</label>
          <div style="display: flex; gap: 16px; margin-top: 8px;">
            <label style="display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 13px; color: #cbd5e1;">
              <input type="radio" name="bookScope" value="all" checked onchange="onBookScopeChange()"> All 100 Followers
            </label>
            <label style="display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 13px; color: #cbd5e1;">
              <input type="radio" name="bookScope" value="range" onchange="onBookScopeChange()"> Index Range
            </label>
            <label style="display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 13px; color: #cbd5e1;">
              <input type="radio" name="bookScope" value="single" onchange="onBookScopeChange()"> Single Account
            </label>
          </div>

          <div id="bookRangeRow" style="display: none; gap: 10px; margin-top: 10px; align-items: center;">
            <span style="font-size: 12px; color: var(--text-muted);">From:</span>
            <input type="number" id="bookStartIdx" value="1" min="1" max="100" class="fleet-input" style="width: 70px;">
            <span style="font-size: 12px; color: var(--text-muted);">To:</span>
            <input type="number" id="bookEndIdx" value="100" min="1" max="100" class="fleet-input" style="width: 70px;">
          </div>
          <div id="bookSingleRow" style="display: none; margin-top: 10px;">
            <select id="bookSingleSelect" class="fleet-input" style="width: 100%;"></select>
          </div>
        </div>

        <!-- Book Selection -->
        <div>
          <label style="font-size: 12px; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">2. Target Book</label>
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 8px;">
            <button type="button" class="fleet-mode-btn" id="btnBookB" onclick="selectFleetBook('b')">
              <div style="font-weight: 700; color: #60a5fa;">📘 B-Book</div>
              <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">Booked on Engine</div>
            </button>
            <button type="button" class="fleet-mode-btn active" id="btnBookA" onclick="selectFleetBook('a')">
              <div style="font-weight: 700; color: #fbbf24;">📙 A-Book</div>
              <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">Liquidity Provider (Real)</div>
            </button>
          </div>
        </div>

        <div style="background: rgba(0,0,0,0.3); padding: 12px 14px; border-radius: 8px; font-size: 12px; color: #cbd5e1; border: 1px dashed rgba(245, 158, 11, 0.3);">
          ℹ️ <strong>A-Book</strong>: Real orders are sent to Liquidity Provider.<br>
          <strong>B-Book</strong>: Real orders are booked internally on the matching engine.
        </div>

        <button class="btn" id="btnApplyBook" onclick="applyFleetBook()" style="background: linear-gradient(135deg, #d97706 0%, #f59e0b 100%); color: #fff; padding: 12px 20px; font-size: 14px; font-weight: 700; width: 100%; justify-content: center; border: none; border-radius: 8px;">
          🔄 Convert Fleet Book via Admin API
        </button>
        <div id="bookStatusBox" style="display: none; padding: 12px; border-radius: 8px; font-size: 12px; background: rgba(30, 41, 59, 0.5); border: 1px solid var(--card-border);"></div>
      </div>

    </div>

    <!-- FLEET ACTIVITY LOG -->
    <div class="table-card">
      <div style="font-weight: 700; font-size: 14px; margin-bottom: 12px; color: #fff; display: flex; justify-content: space-between; align-items: center;">
        <span>📋 Follower Fleet Management Activity Log</span>
        <button class="btn" style="padding: 4px 10px; font-size: 11px;" onclick="clearFleetLog()">Clear Log</button>
      </div>
      <div id="fleetActivityLog" style="max-height: 200px; overflow-y: auto; font-family: 'JetBrains Mono', monospace; font-size: 12px; background: rgba(7, 9, 14, 0.8); border: 1px solid var(--card-border); border-radius: 8px; padding: 12px; line-height: 1.6;">
        <div style="color: var(--text-dim);">[SYSTEM] Follower Fleet Control Center ready. Select category or balance configuration above to execute across followers.</div>
      </div>
    </div>
  </div>

  <!-- MODAL 5: QUICK MANAGE FOLLOWER MODAL -->
  <div class="modal-backdrop" id="quickManageModal" onclick="closeModalOnBackdrop(event)">
    <div class="modal-window" style="max-width: 640px; max-height: 90vh; overflow-y: auto;">
      <div class="modal-header">
        <div>
          <h2 id="quickManageEmail">mamfollower1@mailinator.com</h2>
          <p id="quickManageSub">Quick Account Controller: Category, Multiplier, Book, Broker & Dual Balances</p>
        </div>
        <button class="modal-close" onclick="closeModal('quickManageModal')">&times;</button>
      </div>

      <div class="modal-body" style="display: flex; flex-direction: column; gap: 16px;">
        <!-- 1. MAM Category & Multiplier -->
        <div style="background: rgba(255,255,255,0.02); padding: 14px; border-radius: 8px; border: 1px solid var(--card-border);">
          <div style="font-size: 11px; font-weight: 700; color: var(--accent); text-transform: uppercase; margin-bottom: 8px;">1. Replication Sizing & Multiplier</div>
          <div>
            <label style="font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">MAM Category</label>
            <select id="qmCategory" class="fleet-input" style="width: 100%; margin-top: 6px;" onchange="onQmCategoryChange()">
              <option value="multiplier">Multiplier Mode</option>
              <option value="equity">Equity Based</option>
              <option value="balance">Balance Based</option>
            </select>
          </div>

          <div id="qmMultiplierRow" style="margin-top: 10px;">
            <label style="font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">Multiplier (e.g. 2.0x)</label>
            <input type="number" id="qmMultiplier" value="2.0" step="0.1" min="0.1" max="10.0" class="fleet-input" style="width: 100%; margin-top: 6px;">
          </div>

          <div style="display: flex; gap: 8px; margin-top: 12px;">
            <button class="btn btn-action-primary" style="flex: 2; padding: 8px; justify-content: center;" onclick="saveQuickManageCategory()">Save Sizing Category</button>
            <button class="btn" style="flex: 1; padding: 8px; justify-content: center; background: #dc2626; color: white; border: none; border-radius: 6px; cursor: pointer;" onclick="quickManageLeaveMaster()">🚪 Leave Master</button>
          </div>
        </div>

        <!-- 2. Book Conversion (Admin API) -->
        <div style="background: rgba(255,255,255,0.02); padding: 14px; border-radius: 8px; border: 1px solid var(--card-border);">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <div style="font-size: 11px; font-weight: 700; color: var(--gold); text-transform: uppercase;">2. Book Conversion (Admin API)</div>
            <span id="qmCurrentBookBadge" class="badge badge-mult">📘 B-BOOK</span>
          </div>
          <div style="font-size: 11px; color: var(--text-dim); margin-bottom: 10px;">Switch execution engine routing between B-Book (Internal) and A-Book (Liquidity Provider).</div>
          <div style="display: flex; gap: 10px;">
            <button class="btn btn-book-b" style="flex: 1; padding: 8px; justify-content: center;" onclick="saveQuickManageBook('b')">📘 Switch to B-Book</button>
            <button class="btn btn-book-a" style="flex: 1; padding: 8px; justify-content: center;" onclick="saveQuickManageBook('a')">📙 Switch to A-Book</button>
          </div>
        </div>

        <!-- 3. Broker Settings (Trades Module Settings) -->
        <div style="background: rgba(255,255,255,0.02); padding: 14px; border-radius: 8px; border: 1px solid var(--card-border);">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <div style="font-size: 11px; font-weight: 700; color: var(--accent-real); text-transform: uppercase;">3. Broker Settings (Trades &rarr; Settings)</div>
            <span id="qmCurrentBrokerBadge" class="badge badge-env-real">💎 REAL (HEDGING)</span>
          </div>
          <div style="font-size: 11px; color: var(--text-dim); margin-bottom: 10px;">Enable or disable broker setting environments for this follower account.</div>
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
            <div style="background: #1e293b; padding: 10px; border-radius: 6px; display: flex; justify-content: space-between; align-items: center;">
              <span style="font-size: 12px; font-weight: 600; color: #cbd5e1;">Paper (Hedging)</span>
              <div style="display: flex; gap: 6px;">
                <button class="btn" style="padding: 4px 8px; font-size: 11px; background: #059669; color: white; border: none;" onclick="quickManageToggleBroker('paper', 'enable')">Enable</button>
                <button class="btn" style="padding: 4px 8px; font-size: 11px; background: #dc2626; color: white; border: none;" onclick="quickManageToggleBroker('paper', 'disable')">Disable</button>
              </div>
            </div>
            <div style="background: #1e293b; padding: 10px; border-radius: 6px; display: flex; justify-content: space-between; align-items: center;">
              <span style="font-size: 12px; font-weight: 600; color: #f472b6;">Real (Hedging)</span>
              <div style="display: flex; gap: 6px;">
                <button class="btn" style="padding: 4px 8px; font-size: 11px; background: #059669; color: white; border: none;" onclick="quickManageToggleBroker('real', 'enable')">Enable</button>
                <button class="btn" style="padding: 4px 8px; font-size: 11px; background: #dc2626; color: white; border: none;" onclick="quickManageToggleBroker('real', 'disable')">Disable</button>
              </div>
            </div>
            <div style="background: #1e293b; padding: 10px; border-radius: 6px; display: flex; justify-content: space-between; align-items: center;">
              <span style="font-size: 12px; font-weight: 600; color: #94a3b8;">Paper (Netting)</span>
              <div style="display: flex; gap: 6px;">
                <button class="btn" style="padding: 4px 8px; font-size: 11px; background: #059669; color: white; border: none;" onclick="quickManageToggleBroker('paper-net', 'enable')">Enable</button>
                <button class="btn" style="padding: 4px 8px; font-size: 11px; background: #dc2626; color: white; border: none;" onclick="quickManageToggleBroker('paper-net', 'disable')">Disable</button>
              </div>
            </div>
            <div style="background: #1e293b; padding: 10px; border-radius: 6px; display: flex; justify-content: space-between; align-items: center;">
              <span style="font-size: 12px; font-weight: 600; color: #38bdf8;">Real (Netting)</span>
              <div style="display: flex; gap: 6px;">
                <button class="btn" style="padding: 4px 8px; font-size: 11px; background: #059669; color: white; border: none;" onclick="quickManageToggleBroker('real-net', 'enable')">Enable</button>
                <button class="btn" style="padding: 4px 8px; font-size: 11px; background: #dc2626; color: white; border: none;" onclick="quickManageToggleBroker('real-net', 'disable')">Disable</button>
              </div>
            </div>
          </div>
        </div>

        <!-- 4. Capital & Balance Controller (Admin API) -->
        <div style="background: rgba(255,255,255,0.02); padding: 14px; border-radius: 8px; border: 1px solid var(--card-border);">
          <div style="font-size: 11px; font-weight: 700; color: var(--green); text-transform: uppercase; margin-bottom: 8px;">4. Set Balances (Admin API)</div>
          
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
            <div>
              <label style="font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">Paper Balance ($)</label>
              <input type="number" id="qmPaperBalance" value="10000000" step="100000" class="fleet-input" style="width: 100%; margin-top: 6px;">
              <button class="btn btn-action-primary" style="width: 100%; margin-top: 6px; padding: 6px; justify-content: center; font-size: 11px;" onclick="saveQuickManageBalance('paper')">Set Paper Bal</button>
            </div>
            <div>
              <label style="font-size: 11px; font-weight: 700; color: var(--accent-real); text-transform: uppercase;">Real Balance ($)</label>
              <input type="number" id="qmRealBalance" value="10000000" step="100000" class="fleet-input" style="width: 100%; margin-top: 6px;">
              <button class="btn btn-action-real" style="width: 100%; margin-top: 6px; padding: 6px; justify-content: center; font-size: 11px;" onclick="saveQuickManageBalance('real')">Set Real Bal</button>
            </div>
          </div>
        </div>

        <div id="qmStatusBox" style="display: none; padding: 10px; border-radius: 6px; font-size: 12px; font-weight: 600;"></div>
      </div>
    </div>
  </div>

  <script>
    let activeTab = 'master-pos';
    let autoSyncActive = true;
    let syncInterval = null;
    let activeMasterId = 'mam';
    let currentData = {};
    let activeFollowerFilter = 'all';
    let activeMPosModalMarketOrderId = null;

    function switchTab(tabId, element) {
      activeTab = tabId;
      document.querySelectorAll('.tab-item').forEach(b => b.classList.remove('active'));
      element.classList.add('active');

      document.getElementById('tabContentMasterPos').style.display = tabId === 'master-pos' ? 'block' : 'none';
      document.getElementById('tabContentFollowerPos').style.display = tabId === 'follower-pos' ? 'block' : 'none';
      document.getElementById('tabContentFollowersLedger').style.display = tabId === 'followers-ledger' ? 'block' : 'none';
      document.getElementById('tabContentTradeHistory').style.display = tabId === 'trade-history' ? 'block' : 'none';
      document.getElementById('tabContentFleetManager').style.display = tabId === 'fleet-manager' ? 'block' : 'none';
    }

    function onMasterChange() {
      activeMasterId = document.getElementById('masterSelect').value;
      fetchDashboardData();
    }

    function toggleAutoSync() {
      autoSyncActive = !autoSyncActive;
      const btn = document.getElementById('autoSyncBtn');
      if (autoSyncActive) {
        btn.classList.add('active');
        btn.innerText = "Auto-Sync: 1s (LIVE)";
        startAutoSync();
      } else {
        btn.classList.remove('active');
        btn.innerText = "Auto-Sync: PAUSED";
        clearInterval(syncInterval);
      }
    }

    function startAutoSync() {
      clearInterval(syncInterval);
      syncInterval = setInterval(fetchDashboardData, 1000);
    }

    function fmtMoney(num) {
      return '$' + Number(num || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    function formatCategoryBadge(cat, mult, isMaster) {
      if (isMaster) {
        return `<span class="badge badge-cat-master">👑 MAM MASTER</span>`;
      }
      const c = String(cat || 'multiplier').toLowerCase();
      if (c === 'unfollowed' || c === 'none' || c === 'leave' || c.includes('unfollow')) {
        return `<span class="badge" style="background: rgba(239, 68, 68, 0.2); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.4);">🚪 UNFOLLOWED</span>`;
      } else if (c.includes('equity')) {
        return `<span class="badge badge-cat-equity">⚖️ EQUITY BASED</span>`;
      } else if (c.includes('balance')) {
        return `<span class="badge badge-cat-balance">💰 BALANCE BASED</span>`;
      } else {
        const mStr = (mult !== undefined && mult !== null) ? ` (${Number(mult).toFixed(1)}x)` : '';
        return `<span class="badge badge-cat-multiplier">✖️ MULTIPLIER${mStr}</span>`;
      }
    }

    async function fetchDashboardData() {
      try {
        const res = await fetch(`/api/data?master=${activeMasterId}`);
        if (!res.ok) return;
        currentData = await res.json();
        if (currentData.meta && currentData.meta.active_environment) syncEnvButtons(currentData.meta.active_environment);
        if (currentData.meta) {
          const st = document.getElementById('liveStatusText');
          if (st) st.innerText = currentData.meta.error ? ('OMS ERROR: ' + currentData.meta.error) : 'OMS LIVE';
        }
        renderAll();
      } catch (e) {
        console.error("Fetch error:", e);
      }
    }

    function renderAll() {
      const summary = currentData.summary || {};
      const master = currentData.master || {};
      const masterPos = currentData.master_positions || [];
      const followerPos = currentData.follower_positions || [];
      const followers = currentData.followers || [];
      const history = currentData.history || [];

      // 6 New Summary KPI Cards
      document.getElementById('kpiMasterBal').innerText = fmtMoney(summary.master_balance);
      document.getElementById('kpiMasterEq').innerText = fmtMoney(summary.master_equity);
      document.getElementById('kpiFollowerBal').innerText = fmtMoney(summary.total_follower_balance);
      document.getElementById('kpiFollowerEq').innerText = fmtMoney(summary.total_follower_equity);
      document.getElementById('kpiFollowerCount').innerText = summary.follower_count || followers.length;

      // Profit Share Summary Cards
      document.getElementById('kpiProfitSharedToMaster').innerText = fmtMoney(summary.master_shares_total);
      document.getElementById('kpiFollowersProfitKept').innerText = fmtMoney(summary.total_profit_kept_by_followers);
      document.getElementById('kpiAboveHwmCount').innerText = summary.followers_above_hwm_count || 0;

      // Master Total Earnings
      document.getElementById('kpiMasterTotalEarnings').innerText = fmtMoney(summary.master_total_earnings);
      document.getElementById('kpiMasterTradePnl').innerText = fmtMoney(summary.master_trading_pnl);
      document.getElementById('kpiMasterSharesSub').innerText = fmtMoney(summary.master_shares_total);

      // Replication & Positions
      document.getElementById('kpiRepRate').innerText = (summary.active_replication_rate || 100.0) + '%';
      document.getElementById('kpiOpenPositions').innerText = `${masterPos.length + followerPos.length} (Master: ${summary.master_open_lots || 0}L, Followers: ${summary.total_follower_open_lots || 0}L)`;

      // Master MAM Share Info
      const mamSharePct = (master.mam_share_percent !== undefined) ? master.mam_share_percent : 50;
      const mamDispName = master.mam_display_name || 'mammaster';
      const mShareBadge = document.getElementById('currentMasterShareBadge');
      if (mShareBadge) mShareBadge.innerText = `MY SHARE: ${mamSharePct}%`;
      const fInherited = document.getElementById('followerInheritedShare');
      if (fInherited) fInherited.innerText = `${mamSharePct}% (Decided by Master)`;

      // Master Banner
      document.getElementById('mAvatar').innerText = (master.type || 'M')[0];
      document.getElementById('mEmail').innerText = master.email || 'N/A';
      document.getElementById('mSubText').innerText = `${master.name || master.type} (Member ID: ${master.member_id || 'N/A'})`;
      document.getElementById('mPnl').innerText = fmtMoney(master.unrealized_pnl);
      document.getElementById('mFreeMargin').innerText = fmtMoney(master.free_margin);
      document.getElementById('mWinRate').innerText = (summary.win_rate_percent || 0.0) + '%';
      document.getElementById('mLastSync').innerText = currentData.meta ? currentData.meta.last_updated : '--:--:--';

      // Tab Badges
      document.getElementById('badgeMasterPos').innerText = masterPos.length;
      document.getElementById('badgeFollowerPos').innerText = followerPos.length;
      document.getElementById('badgeFollowers').innerText = followers.length;
      document.getElementById('badgeHistory').innerText = history.length;
      document.getElementById('pillAllCount').innerText = followers.length;
      document.getElementById('badgeFleetManager').innerText = followers.length;

      // Populate Fleet Manager Dropdowns
      populateFleetDropdowns();

      // Render Tables
      renderMasterPositions();
      renderFollowerPositions();
      renderFollowersLedger();
      renderHistoryTable();

      // Live-sync active Master Position modal in real-time
      const mModal = document.getElementById('masterPosFollowersModal');
      if (activeMPosModalMarketOrderId && mModal && mModal.style.display === 'flex') {
        openMasterPosFollowersModal(activeMPosModalMarketOrderId, true);
      }
    }

    // 1. Master Active Positions Table
    function renderMasterPositions() {
      const tbody = document.getElementById('masterPositionsBody');
      const positions = currentData.master_positions || [];

      if (positions.length === 0) {
        tbody.innerHTML = '<tr><td colspan="17" class="empty-row">No active open positions on Master account. Clean slate.</td></tr>';
        return;
      }

      tbody.innerHTML = positions.map(p => {
        const sideClass = (p.side || '').toUpperCase() === 'BUY' ? 'badge-buy' : 'badge-sell';
        const pnl = Number(p.unrealized_pnl || 0);
        const pnlClass = pnl > 0 ? 'text-green' : (pnl < 0 ? 'text-red' : '');
        const orderType = (p.type || p.order_type || 'MARKET').toUpperCase();
        const tpVal = p.tp ? `<span class="badge badge-tp">${Number(p.tp).toFixed(2)}</span>` : '<span style="color:var(--text-dim);">-</span>';
        const slVal = p.sl ? `<span class="badge badge-sl">${Number(p.sl).toFixed(2)}</span>` : '<span style="color:var(--text-dim);">-</span>';
        const tslVal = p.tsl ? `<span class="badge">${Number(p.tsl).toFixed(2)}</span>` : '<span style="color:var(--text-dim);">-</span>';
        const timeStr = p.time ? String(p.time).replace('T', ' ').substring(0, 19) : '--';
        const mktId = p.market_order_id || p.order_id || 'N/A';

        return `<tr class="clickable-row" onclick="openMasterPosFollowersModal('${mktId}')" title="Click to view all 100 follower copied orders">
          <td><span class="badge badge-master">MASTER</span></td>
          <td style="font-weight: 700;">${p.account}</td>
          <td style="font-size: 11px; color: #60a5fa; font-weight: 700;">${mktId}</td>
          <td><span class="badge badge-cat-master">👑 MAM MASTER</span></td>
          <td><strong>${p.symbol}</strong></td>
          <td><span class="badge badge-type">${orderType}</span></td>
          <td><span class="badge ${sideClass}">${p.side}</span></td>
          <td style="font-weight: 800; font-size: 14px; color: #38bdf8;">${Number(p.net_qty || p.qty || 0).toFixed(2)}</td>
          <td>${tpVal}</td>
          <td>${slVal}</td>
          <td>${tslVal}</td>
          <td>${Number(p.avg_entry_price || p.fill_price || 0).toFixed(2)}</td>
          <td>${Number(p.current_price || p.avg_entry_price || 0).toFixed(2)}</td>
          <td class="${pnlClass}">${fmtMoney(pnl)}</td>
          <td style="font-size: 11px; color: var(--text-muted);">${timeStr}</td>
          <td><span class="badge badge-buy">ACTIVE</span></td>
          <td>
            <button class="btn btn-view-followers" onclick="event.stopPropagation(); openMasterPosFollowersModal('${mktId}')">⚡ View Followers</button>
          </td>
        </tr>`;
      }).join('');
    }

    // 2. Follower Active Positions Table
    function renderFollowerPositions() {
      const tbody = document.getElementById('followerPositionsBody');
      const allPos = currentData.follower_positions || [];
      const search = (document.getElementById('followerPosSearch').value || '').toLowerCase();

      const filtered = allPos.filter(p => (p.account || '').toLowerCase().includes(search) || (p.symbol || '').toLowerCase().includes(search));
      document.getElementById('followerPosFilteredCount').innerText = filtered.length;

      if (filtered.length === 0) {
        tbody.innerHTML = '<tr><td colspan="17" class="empty-row">No open replicated follower positions active.</td></tr>';
        return;
      }

      tbody.innerHTML = filtered.map(p => {
        const sideClass = (p.side || '').toUpperCase() === 'BUY' ? 'badge-buy' : 'badge-sell';
        const pnl = Number(p.unrealized_pnl || 0);
        const pnlClass = pnl > 0 ? 'text-green' : (pnl < 0 ? 'text-red' : '');
        const orderType = (p.type || p.order_type || 'MARKET').toUpperCase();
        const tpVal = p.tp ? `<span class="badge badge-tp">${Number(p.tp).toFixed(2)}</span>` : '<span style="color:var(--text-dim);">-</span>';
        const slVal = p.sl ? `<span class="badge badge-sl">${Number(p.sl).toFixed(2)}</span>` : '<span style="color:var(--text-dim);">-</span>';
        const tslVal = p.tsl ? `<span class="badge">${Number(p.tsl).toFixed(2)}</span>` : '<span style="color:var(--text-dim);">-</span>';
        const mQty = p.master_qty ? Number(p.master_qty).toFixed(2) : '-';
        const mult = p.multiplier ? `${Number(p.multiplier).toFixed(1)}x` : '1.0x';
        const fMktId = p.market_order_id || 'N/A';

        return `<tr>
          <td style="font-weight: 700;">${p.account}</td>
          <td style="font-size: 11px; color: var(--text-muted);">${fMktId}</td>
          <td>
            <button class="btn btn-view-master" onclick="event.stopPropagation(); openMasterDetailModal('${fMktId}')">🎯 View Master</button>
          </td>
          <td>${formatCategoryBadge(p.category || p.method, p.multiplier, false)}</td>
          <td><strong>${p.symbol}</strong></td>
          <td><span class="badge badge-type">${orderType}</span></td>
          <td><span class="badge ${sideClass}">${p.side}</span></td>
          <td style="font-weight: 800; font-size: 14px; color: #4ade80;">${Number(p.net_qty || p.qty || 0).toFixed(2)}</td>
          <td style="font-weight: 700; color: #38bdf8;">${mQty}</td>
          <td><span class="badge badge-mult">${mult}</span></td>
          <td>${tpVal}</td>
          <td>${slVal}</td>
          <td>${tslVal}</td>
          <td>${Number(p.avg_entry_price || p.fill_price || 0).toFixed(2)}</td>
          <td>${Number(p.current_price || p.avg_entry_price || 0).toFixed(2)}</td>
          <td class="${pnlClass}">${fmtMoney(pnl)}</td>
          <td><span class="badge badge-synced">SYNCED</span></td>
        </tr>`;
      }).join('');
    }

    // 3. Followers Ledger Table with Profit Shares & Click Handler
    function setFollowerFilter(type, el) {
      activeFollowerFilter = type;
      document.querySelectorAll('.f-pill').forEach(p => p.classList.remove('active'));
      el.classList.add('active');
      renderFollowersLedger();
    }

    function renderFollowersLedger() {
      const tbody = document.getElementById('followersLedgerBody');
      const followers = currentData.followers || [];
      const search = (document.getElementById('followerSearch').value || '').toLowerCase();

      const list = followers.filter(f => {
        const match = f.email.toLowerCase().includes(search) || f.name.toLowerCase().includes(search);
        if (!match) return false;
        if (activeFollowerFilter === 'open') return f.open_positions_count > 0;
        if (activeFollowerFilter === 'hwm') return f.above_benchmark === true;
        return true;
      });

      if (list.length === 0) {
        tbody.innerHTML = '<tr><td colspan="12" class="empty-row">No followers match current filter.</td></tr>';
        return;
      }

      tbody.innerHTML = list.map((f, i) => {
        const aboveBadge = f.above_benchmark
          ? '<span class="badge badge-hwm-yes">YES (Above)</span>'
          : '<span class="badge badge-hwm-no">AT HWM</span>';
        const pnl = Number(f.unrealized_pnl || 0);
        const pnlClass = pnl > 0 ? 'text-green' : (pnl < 0 ? 'text-red' : '');

        const bookBtn = f.book === 'a'
          ? `<button class="btn-book-a" onclick="event.stopPropagation(); toggleFollowerBook('${f.email}', 'b')" title="Click to convert to B-Book">📙 A-BOOK</button>`
          : `<button class="btn-book-b" onclick="event.stopPropagation(); toggleFollowerBook('${f.email}', 'a')" title="Click to convert to A-Book">📘 B-BOOK</button>`;
        const brokerBadge = `<span class="${instBadgeClass(f.broker_setting)}">${instBadgeHtml(f.broker_setting)}</span>`;

        return `<tr class="clickable-row" onclick="openFollowerModal('${f.email}')" title="Click to view full order history & profit share breakdown">
          <td style="color: var(--text-dim);">${i + 1}</td>
          <td style="font-weight: 700; color: #60a5fa;">
            ${f.email} <span style="font-size: 11px; color: var(--text-dim); margin-left: 4px;">🔍</span>
          </td>
          <td>${bookBtn}</td>
          <td>${brokerBadge}</td>
          <td>${formatCategoryBadge(f.category || f.method, f.multiplier, false)}</td>
          <td><strong>${fmtMoney(f.paper_balance !== undefined ? f.paper_balance : f.balance)}</strong></td>
          <td style="color: #f472b6;"><strong>${fmtMoney(f.real_balance || 0)}</strong></td>
          <td>${fmtMoney(f.equity)}</td>
          <td style="font-weight: 600;">${fmtMoney(f.benchmark)}</td>
          <td>${aboveBadge}</td>
          <td><span class="badge badge-shared">+${fmtMoney(f.shared_to_master)}</span></td>
          <td class="text-green" style="font-weight: 700;">+${fmtMoney(f.profit_kept)}</td>
          <td>
            <div style="display: flex; gap: 6px;">
              <button class="btn" style="padding: 4px 8px; font-size: 11px; background: rgba(59, 130, 246, 0.2); border-color: rgba(59, 130, 246, 0.4); color: #60a5fa;" onclick="event.stopPropagation(); openQuickManageModal('${f.email}')">⚙️ Control</button>
              <button class="btn" style="padding: 4px 10px; font-size: 11px;" onclick="event.stopPropagation(); openFollowerModal('${f.email}')">History</button>
            </div>
          </td>
        </tr>`;
      }).join('');
    }

    // 4. Closed Trade History Table
    function renderHistoryTable() {
      const tbody = document.getElementById('historyTableBody');
      const history = currentData.history || [];
      const search = (document.getElementById('historySearch').value || '').toLowerCase();

      const list = history.filter(h =>
        (h.symbol || '').toLowerCase().includes(search) ||
        (h.order_id || '').toLowerCase().includes(search)
      );

      document.getElementById('histTotalCount').innerText = history.length;
      const totalPnl = history.reduce((sum, h) => sum + Number(h.realized_pnl || 0), 0);
      const pnlEl = document.getElementById('histTotalPnl');
      pnlEl.innerText = fmtMoney(totalPnl);
      pnlEl.className = totalPnl >= 0 ? 'text-green' : 'text-red';

      if (list.length === 0) {
        tbody.innerHTML = '<tr><td colspan="16" class="empty-row">No closed trade records found.</td></tr>';
        return;
      }

      tbody.innerHTML = list.map(h => {
        const sideClass = (h.side || '').toUpperCase() === 'BUY' ? 'badge-buy' : 'badge-sell';
        const pnl = Number(h.realized_pnl || 0);
        const pnlClass = pnl > 0 ? 'text-green' : (pnl < 0 ? 'text-red' : '');
        const timeStr = h.executed_at ? h.executed_at.replace('T', ' ').slice(0, 19) : 'N/A';
        const orderType = (h.type || h.entry_type || 'MARKET').toUpperCase();
        const tpVal = h.tp ? `<span class="badge badge-tp">${Number(h.tp).toFixed(2)}</span>` : '<span style="color:var(--text-dim);">-</span>';
        const slVal = h.sl ? `<span class="badge badge-sl">${Number(h.sl).toFixed(2)}</span>` : '<span style="color:var(--text-dim);">-</span>';
        const tslVal = h.tsl ? `<span class="badge">${Number(h.tsl).toFixed(2)}</span>` : '<span style="color:var(--text-dim);">-</span>';

        return `<tr class="clickable-row" onclick="openMasterHistFollowersModal(${h.history_id})" title="Click to view all followers who copied this closed trade">
          <td style="color: var(--text-dim); font-size: 11px;">#${h.history_id || 'N/A'}</td>
          <td style="font-size: 11px; color: var(--text-muted);">${timeStr}</td>
          <td><span class="badge badge-cat-master">👑 MAM MASTER</span></td>
          <td><strong>${h.symbol}</strong></td>
          <td><span class="badge badge-type">${orderType}</span></td>
          <td><span class="badge ${sideClass}">${h.side}</span></td>
          <td style="font-weight: 800; font-size: 13px; color: #38bdf8;">${Number(h.qty || 0).toFixed(2)}</td>
          <td>${tpVal}</td>
          <td>${slVal}</td>
          <td>${tslVal}</td>
          <td>${Number(h.entry_price || 0).toFixed(2)}</td>
          <td>${Number(h.exit_price || 0).toFixed(2)}</td>
          <td class="${pnlClass}" style="font-weight: 700;">${fmtMoney(pnl)}</td>
          <td style="font-size: 11px; text-transform: uppercase;">${h.exit_source || h.exit_type || 'N/A'}</td>
          <td style="font-size: 11px; color: var(--text-muted);">${h.entry_copy_kind || h.attribution || 'master'}</td>
          <td>
            <button class="btn btn-view-followers" onclick="event.stopPropagation(); openMasterHistFollowersModal(${h.history_id})">⚡ View Followers</button>
          </td>
        </tr>`;
      }).join('');
    }

    // 5. Follower Order History Modal Logic
    function openFollowerModal(email) {
      const followers = currentData.followers || [];
      const f = followers.find(x => x.email === email);
      if (!f) return;

      document.getElementById('modalFollowerEmail').innerText = f.email;
      document.getElementById('modalFollowerSub').innerText = `Member ID: ${f.member_id} | Sizing: ${f.method} (${f.multiplier}x)`;
      document.getElementById('modalMgrName').innerText = f.following || 'mammaster (50%)';
      document.getElementById('modalBenchmark').innerText = fmtMoney(f.benchmark);
      document.getElementById('modalBalance').innerText = fmtMoney(f.balance);
      document.getElementById('modalSharedTotal').innerText = `+${fmtMoney(f.shared_to_master)}`;
      document.getElementById('modalKeptTotal').innerText = `+${fmtMoney(f.profit_kept)}`;

      const tbody = document.getElementById('modalSharesTableBody');
      const shares = f.shares_history || [];

      if (shares.length === 0) {
        tbody.innerHTML = '<tr><td colspan="16" class="empty-row">No trade profit shares recorded for this follower yet.</td></tr>';
      } else {
        tbody.innerHTML = shares.map(s => {
          const orderPnl = Number(s.order_pnl || s.trade_pnl || 0);
          const mgrShare = Number(s.master_share || 0);
          const kept = Number(s.follower_share || 0);
          const isAbove = s.above_hwm;
          const aboveBadge = isAbove
            ? '<span class="badge badge-hwm-yes">YES (Shared)</span>'
            : '<span class="badge badge-hwm-no">NO (0% Taken)</span>';
          const timeStr = s.at ? s.at.replace('T', ' ').slice(0, 19) : 'N/A';
          const pnlColor = orderPnl > 0 ? 'text-green' : (orderPnl < 0 ? 'text-red' : '');
          const sideClass = (s.side || '').toUpperCase() === 'BUY' ? 'badge-buy' : 'badge-sell';
          const orderType = (s.type || 'MARKET').toUpperCase();
          const tpVal = s.tp ? `<span class="badge badge-tp">${Number(s.tp).toFixed(2)}</span>` : '<span style="color:var(--text-dim);">-</span>';
          const slVal = s.sl ? `<span class="badge badge-sl">${Number(s.sl).toFixed(2)}</span>` : '<span style="color:var(--text-dim);">-</span>';
          const tslVal = s.tsl ? `<span class="badge">${Number(s.tsl).toFixed(2)}</span>` : '<span style="color:var(--text-dim);">-</span>';
          const mQty = s.master_qty ? Number(s.master_qty).toFixed(2) : '-';

          return `<tr>
            <td style="font-size: 11px; color: var(--text-dim);">#${s.trade_id || s.share_id || 'N/A'}</td>
            <td style="font-size: 11px; color: var(--text-muted);">${timeStr}</td>
            <td>${formatCategoryBadge(s.category || s.method || f.method, s.multiplier || f.multiplier, false)}</td>
            <td><strong>${s.symbol || 'BINANCE:BTCUSDT.P'}</strong></td>
            <td><span class="badge badge-type">${orderType}</span></td>
            <td><span class="badge ${sideClass}">${s.side || 'BUY'}</span></td>
            <td style="font-weight: 800; font-size: 13px; color: #4ade80;">${Number(s.qty || 0).toFixed(2)}</td>
            <td style="font-weight: 700; color: #38bdf8;">${mQty}</td>
            <td>${tpVal}</td>
            <td>${slVal}</td>
            <td>${tslVal}</td>
            <td class="${pnlColor}" style="font-weight: 700;">${fmtMoney(orderPnl)}</td>
            <td>${fmtMoney(s.balance_before)}</td>
            <td>${aboveBadge}</td>
            <td class="text-gold" style="font-weight: 700;">+${fmtMoney(mgrShare)}</td>
            <td class="text-green" style="font-weight: 700;">+${fmtMoney(kept)}</td>
          </tr>`;
        }).join('');
      }

      document.getElementById('followerModal').style.display = 'flex';
    }

    function closeFollowerModal() {
      document.getElementById('followerModal').style.display = 'none';
    }

    function closeModal(modalId) {
      const el = document.getElementById(modalId);
      if (el) el.style.display = 'none';
      if (modalId === 'masterPosFollowersModal') activeMPosModalMarketOrderId = null;
    }

    function closeModalOnBackdrop(e) {
      if (e.target.classList.contains('modal-backdrop')) {
        e.target.style.display = 'none';
        activeMPosModalMarketOrderId = null;
      }
    }

    // 6. Master Active Order -> Replicated Followers Modal
    function openMasterPosFollowersModal(marketOrderId, isLiveRefresh = false) {
      activeMPosModalMarketOrderId = marketOrderId;
      const positions = currentData.master_positions || [];
      const m = positions.find(p => (p.market_order_id === marketOrderId || p.order_id === marketOrderId)) || positions[0];
      if (!m) return;

      document.getElementById('mPosModalTitle').innerText = `🎯 Master Order: ${m.symbol} (${m.side}) - Replicated Followers`;
      document.getElementById('mPosModalSub').innerText = `Master Order ID: ${m.market_order_id || m.order_id} | Qty: ${Number(m.net_qty || m.qty || 0).toFixed(2)} Lots | Fill: ${Number(m.avg_entry_price || 0).toFixed(2)}`;

      const allFollowerPos = currentData.follower_positions || [];
      const matchingFollowers = allFollowerPos.filter(f => 
        (f.group_id && m.group_id && f.group_id === m.group_id) ||
        (f.symbol === m.symbol && f.side === m.side)
      );

      document.getElementById('mPosFollowerCount').innerText = matchingFollowers.length;

      const totFollowerLots = matchingFollowers.reduce((s, f) => s + Number(f.net_qty || f.qty || 0), 0);
      const totFollowerPnl = matchingFollowers.reduce((s, f) => s + Number(f.unrealized_pnl || 0), 0);

      document.getElementById('mPosModalStats').innerHTML = `
        <div class="modal-stat-box">
          <div>Master Lot Size</div>
          <div style="color: #38bdf8; font-weight: 800; font-size: 15px;">${Number(m.net_qty || m.qty || 0).toFixed(2)} Lots</div>
        </div>
        <div class="modal-stat-box">
          <div>Total Follower Volume</div>
          <div style="color: #4ade80; font-weight: 800; font-size: 15px;">${totFollowerLots.toFixed(2)} Lots (${matchingFollowers.length} Accounts)</div>
        </div>
        <div class="modal-stat-box">
          <div>Master Entry / Mark</div>
          <div>${Number(m.avg_entry_price || 0).toFixed(2)} / ${Number(m.current_price || 0).toFixed(2)}</div>
        </div>
        <div class="modal-stat-box">
          <div>Master Unrealized P&L</div>
          <div class="${Number(m.unrealized_pnl || 0) >= 0 ? 'text-green' : 'text-red'}">${fmtMoney(m.unrealized_pnl)}</div>
        </div>
        <div class="modal-stat-box">
          <div>Followers Pool P&L</div>
          <div class="${totFollowerPnl >= 0 ? 'text-green' : 'text-red'}">${fmtMoney(totFollowerPnl)}</div>
        </div>
      `;

      const tbody = document.getElementById('mPosFollowersTableBody');
      if (matchingFollowers.length === 0) {
        tbody.innerHTML = '<tr><td colspan="16" class="empty-row">No follower positions found for this master order.</td></tr>';
      } else {
        tbody.innerHTML = matchingFollowers.map(f => {
          const sideClass = (f.side || '').toUpperCase() === 'BUY' ? 'badge-buy' : 'badge-sell';
          const pnl = Number(f.unrealized_pnl || 0);
          const pnlClass = pnl > 0 ? 'text-green' : (pnl < 0 ? 'text-red' : '');
          const orderType = (f.type || 'MARKET').toUpperCase();
          const tpNum = f.tp || m.tp;
          const slNum = f.sl || m.sl;
          const tslNum = f.tsl || m.tsl;
          const tpVal = tpNum ? `<span class="badge badge-tp">${Number(tpNum).toFixed(2)}</span>` : '<span style="color:var(--text-dim);">-</span>';
          const slVal = slNum ? `<span class="badge badge-sl">${Number(slNum).toFixed(2)}</span>` : '<span style="color:var(--text-dim);">-</span>';
          const tslVal = tslNum ? `<span class="badge">${Number(tslNum).toFixed(2)}</span>` : '<span style="color:var(--text-dim);">-</span>';

          return `<tr>
            <td style="font-weight: 700; color: #60a5fa;">${f.account}</td>
            <td style="font-size: 11px; color: var(--text-muted);">${f.market_order_id || 'N/A'}</td>
            <td>${formatCategoryBadge(f.category || f.method, f.multiplier, false)}</td>
            <td><strong>${f.symbol}</strong></td>
            <td><span class="badge badge-type">${orderType}</span></td>
            <td><span class="badge ${sideClass}">${f.side}</span></td>
            <td style="font-weight: 800; font-size: 13px; color: #4ade80;">${Number(f.net_qty || f.qty || 0).toFixed(2)}</td>
            <td style="font-weight: 700; color: #38bdf8;">${Number(m.net_qty || m.qty || 0).toFixed(2)}</td>
            <td><span class="badge badge-mult">${f.multiplier || 2.0}x</span></td>
            <td>${tpVal}</td>
            <td>${slVal}</td>
            <td>${tslVal}</td>
            <td>${Number(f.avg_entry_price || 0).toFixed(2)}</td>
            <td>${Number(f.current_price || m.current_price || 0).toFixed(2)}</td>
            <td class="${pnlClass}">${fmtMoney(pnl)}</td>
            <td><span class="badge badge-synced">SYNCED</span></td>
          </tr>`;
        }).join('');
      }

      if (!isLiveRefresh) {
        document.getElementById('masterPosFollowersModal').style.display = 'flex';
      }
    }

    // 7. Follower Position -> View Originating Master Trade
    function openMasterDetailModal(followerMktOrderId) {
      const allFollowerPos = currentData.follower_positions || [];
      const f = allFollowerPos.find(p => (p.market_order_id === followerMktOrderId || p.order_id === followerMktOrderId)) || allFollowerPos[0];
      if (!f) return;

      const masterPositions = currentData.master_positions || [];
      const m = masterPositions.find(p =>
        (f.group_id && p.group_id && f.group_id === p.group_id) ||
        (f.symbol === p.symbol && f.side === p.side)
      ) || masterPositions[0] || {};

      document.getElementById('fToMTitle').innerText = `🎯 Master Originating Trade: ${m.symbol || f.symbol} (${m.side || f.side})`;
      document.getElementById('fToMSub').innerText = `Follower ${f.account} copied this trade directly from Master (${m.account || 'mammaster@mailinator.com'})`;

      document.getElementById('fToMStats').innerHTML = `
        <div class="modal-stat-box">
          <div>Master Account</div>
          <div style="color: #60a5fa; font-weight: 700;">${m.account || 'mammaster@mailinator.com'}</div>
        </div>
        <div class="modal-stat-box">
          <div>Master Order ID</div>
          <div style="font-size: 11px; color: var(--text-muted);">${m.market_order_id || m.order_id || 'N/A'}</div>
        </div>
        <div class="modal-stat-box">
          <div>Master Lot Size</div>
          <div style="color: #38bdf8; font-weight: 800; font-size: 15px;">${Number(m.net_qty || m.qty || 1.0).toFixed(2)} Lots</div>
        </div>
        <div class="modal-stat-box">
          <div>Master Entry Price</div>
          <div>${Number(m.avg_entry_price || f.avg_entry_price || 0).toFixed(2)}</div>
        </div>
        <div class="modal-stat-box">
          <div>Master Unrealized P&L</div>
          <div class="${Number(m.unrealized_pnl || 0) >= 0 ? 'text-green' : 'text-red'}">${fmtMoney(m.unrealized_pnl)}</div>
        </div>
      `;

      document.getElementById('fToMBody').innerHTML = `
        <div style="background: rgba(15, 23, 42, 0.6); border: 1px solid var(--card-border); border-radius: 10px; padding: 18px; margin-top: 10px;">
          <h4 style="color: #fff; margin-bottom: 12px; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px;">Master vs Follower Execution Comparison</h4>
          <table style="width: 100%;">
            <thead>
              <tr>
                <th>Attribute</th>
                <th style="color: #38bdf8;">Master Execution</th>
                <th style="color: #4ade80;">Follower (${f.account})</th>
              </tr>
            </thead>
            <tbody>
              <tr><td>Order ID</td><td style="font-size:11px;">${m.market_order_id || m.order_id || 'N/A'}</td><td style="font-size:11px;">${f.market_order_id || 'N/A'}</td></tr>
              <tr><td>Group ID (Sync Token)</td><td colspan="2" style="font-size:11px; color:#c084fc;">${f.group_id || m.group_id || 'Shared Group'}</td></tr>
              <tr><td>Symbol & Side</td><td><strong>${m.symbol || f.symbol}</strong> (${m.side || f.side})</td><td><strong>${f.symbol}</strong> (${f.side})</td></tr>
              <tr><td>Order Type</td><td><span class="badge badge-type">${m.type || 'MARKET'}</span></td><td><span class="badge badge-type">${f.type || 'MARKET'}</span></td></tr>
              <tr><td>Executed Quantity</td><td style="font-weight:800; color:#38bdf8;">${Number(m.net_qty || m.qty || 1.0).toFixed(2)} Lots</td><td style="font-weight:800; color:#4ade80;">${Number(f.net_qty || f.qty || 0).toFixed(2)} Lots</td></tr>
              <tr><td>Category / Mode</td><td><span class="badge badge-cat-master">👑 MAM MASTER</span></td><td>${formatCategoryBadge(f.category || f.method, f.multiplier, false)}</td></tr>
              <tr><td>Sizing Multiplier</td><td>1.0x (Origin)</td><td><span class="badge badge-mult">${f.multiplier || 2.0}x</span></td></tr>
              <tr><td>Entry Price</td><td>${Number(m.avg_entry_price || f.avg_entry_price || 0).toFixed(2)}</td><td>${Number(f.avg_entry_price || 0).toFixed(2)}</td></tr>
              <tr><td>Unrealized P&L</td><td class="${Number(m.unrealized_pnl || 0) >= 0 ? 'text-green' : 'text-red'}">${fmtMoney(m.unrealized_pnl)}</td><td class="${Number(f.unrealized_pnl || 0) >= 0 ? 'text-green' : 'text-red'}">${fmtMoney(f.unrealized_pnl)}</td></tr>
              <tr><td>Replication State</td><td><span class="badge badge-master">MASTER</span></td><td><span class="badge badge-synced">SYNCED</span></td></tr>
            </tbody>
          </table>
        </div>
      `;

      document.getElementById('followerToMasterModal').style.display = 'flex';
    }

    // 8. Master Closed History -> View All Replicated Followers
    function openMasterHistFollowersModal(historyId) {
      const history = currentData.history || [];
      const mHist = history.find(h => h.history_id === historyId) || history[0];
      if (!mHist) return;

      document.getElementById('mHistModalTitle').innerText = `📜 Master Trade #${mHist.history_id} (${mHist.symbol} ${mHist.side}) - Replicated Followers`;
      document.getElementById('mHistModalSub').innerText = `Executed At: ${mHist.executed_at ? mHist.executed_at.replace('T', ' ').slice(0, 19) : 'N/A'} | Entry: ${Number(mHist.entry_price || 0).toFixed(2)} | Exit: ${Number(mHist.exit_price || 0).toFixed(2)} | Realized P&L: ${fmtMoney(mHist.realized_pnl)}`;

      const mTimePrefix = (mHist.executed_at || '').slice(0, 19);
      const followers = currentData.followers || [];
      const matched = [];

      followers.forEach(f => {
        const shares = f.shares_history || [];
        const match = shares.find(sh =>
          (sh.at && sh.at.slice(0, 19) === mTimePrefix) ||
          (sh.symbol === mHist.symbol && Math.abs(new Date(sh.at) - new Date(mHist.executed_at)) < 3000)
        );
        if (match) {
          matched.push({
            email: f.email,
            category: match.category || f.method,
            multiplier: match.multiplier || f.multiplier,
            ...match
          });
        }
      });

      document.getElementById('mHistFollowerCount').innerText = matched.length;

      const totPnl = matched.reduce((s, x) => s + Number(x.order_pnl || x.trade_pnl || 0), 0);
      const totShared = matched.reduce((s, x) => s + Number(x.master_share || 0), 0);
      const totKept = matched.reduce((s, x) => s + Number(x.follower_share || 0), 0);

      document.getElementById('mHistModalStats').innerHTML = `
        <div class="modal-stat-box">
          <div>Master Executed Lot</div>
          <div style="color: #38bdf8; font-weight: 800;">${Number(mHist.qty || 0).toFixed(2)} Lots</div>
        </div>
        <div class="modal-stat-box">
          <div>Master Realized P&L</div>
          <div class="${Number(mHist.realized_pnl || 0) >= 0 ? 'text-green' : 'text-red'}">${fmtMoney(mHist.realized_pnl)}</div>
        </div>
        <div class="modal-stat-box">
          <div>Followers Replicated</div>
          <div style="color: #4ade80; font-weight: 800;">${matched.length} Accounts</div>
        </div>
        <div class="modal-stat-box">
          <div>Follower Shared to Master</div>
          <div class="text-gold">+${fmtMoney(totShared)}</div>
        </div>
        <div class="modal-stat-box">
          <div>Followers Net Profit Kept</div>
          <div class="${totKept >= 0 ? 'text-green' : 'text-red'}">+${fmtMoney(totKept)}</div>
        </div>
      `;

      const tbody = document.getElementById('mHistFollowersTableBody');
      if (matched.length === 0) {
        tbody.innerHTML = '<tr><td colspan="17" class="empty-row">No follower execution ledger records found for this master trade.</td></tr>';
      } else {
        tbody.innerHTML = matched.map(sh => {
          const orderPnl = Number(sh.order_pnl || sh.trade_pnl || 0);
          const mgrShare = Number(sh.master_share || 0);
          const kept = Number(sh.follower_share || 0);
          const isAbove = sh.above_hwm;
          const aboveBadge = isAbove
            ? '<span class="badge badge-hwm-yes">YES (Shared)</span>'
            : '<span class="badge badge-hwm-no">NO (0% Taken)</span>';
          const pnlColor = orderPnl > 0 ? 'text-green' : (orderPnl < 0 ? 'text-red' : '');
          const sideClass = (sh.side || mHist.side || '').toUpperCase() === 'BUY' ? 'badge-buy' : 'badge-sell';
          const orderType = (sh.type || 'MARKET').toUpperCase();
          const tpNum = sh.tp || mHist.tp;
          const slNum = sh.sl || mHist.sl;
          const tslNum = sh.tsl || mHist.tsl;
          const tpVal = tpNum ? `<span class="badge badge-tp">${Number(tpNum).toFixed(2)}</span>` : '<span style="color:var(--text-dim);">-</span>';
          const slVal = slNum ? `<span class="badge badge-sl">${Number(slNum).toFixed(2)}</span>` : '<span style="color:var(--text-dim);">-</span>';
          const tslVal = tslNum ? `<span class="badge">${Number(tslNum).toFixed(2)}</span>` : '<span style="color:var(--text-dim);">-</span>';

          return `<tr>
            <td style="font-weight: 700; color: #60a5fa;">${sh.email}</td>
            <td style="font-size: 11px; color: var(--text-dim);">#${sh.trade_id || sh.share_id || 'N/A'}</td>
            <td>${formatCategoryBadge(sh.category || sh.method, sh.multiplier, false)}</td>
            <td><strong>${sh.symbol || mHist.symbol}</strong></td>
            <td><span class="badge badge-type">${orderType}</span></td>
            <td><span class="badge ${sideClass}">${sh.side || mHist.side}</span></td>
            <td style="font-weight: 800; font-size: 13px; color: #4ade80;">${Number(sh.qty || 0).toFixed(2)}</td>
            <td style="font-weight: 700; color: #38bdf8;">${Number(mHist.qty || 0).toFixed(2)}</td>
            <td>${tpVal}</td>
            <td>${slVal}</td>
            <td>${tslVal}</td>
            <td>${Number(sh.entry_price || mHist.entry_price || 0).toFixed(2)}</td>
            <td>${Number(sh.exit_price || mHist.exit_price || 0).toFixed(2)}</td>
            <td class="${pnlColor}" style="font-weight: 700;">${fmtMoney(orderPnl)}</td>
            <td>${aboveBadge}</td>
            <td class="text-gold" style="font-weight: 700;">+${fmtMoney(mgrShare)}</td>
            <td class="text-green" style="font-weight: 700;">+${fmtMoney(kept)}</td>
          </tr>`;
        }).join('');
      }

      document.getElementById('masterHistFollowersModal').style.display = 'flex';
    }

    // --- 9. Follower Fleet Manager Controller Logic ---
    let selectedFleetCat = 'multiplier';

    function populateFleetDropdowns() {
      const followers = currentData.followers || [];
      const catSelect = document.getElementById('catSingleSelect');
      const balSelect = document.getElementById('balSingleSelect');
      populateBrokerBookDropdowns();
      if (!catSelect || !balSelect) return;

      if (catSelect.options.length !== followers.length) {
        const curCatVal = catSelect.value;
        const curBalVal = balSelect.value;
        catSelect.innerHTML = followers.map(f => `<option value="${f.email}">${f.email} (${f.method} ${f.multiplier}x, ${fmtMoney(f.balance)})</option>`).join('');
        balSelect.innerHTML = followers.map(f => `<option value="${f.email}">${f.email} (${fmtMoney(f.balance)})</option>`).join('');
        if (curCatVal) catSelect.value = curCatVal;
        if (curBalVal) balSelect.value = curBalVal;
      }
    }

    function onCatScopeChange() {
      const scope = document.querySelector('input[name="catScope"]:checked').value;
      document.getElementById('catRangeRow').style.display = scope === 'range' ? 'flex' : 'none';
      document.getElementById('catSingleRow').style.display = scope === 'single' ? 'block' : 'none';
    }

    function onBalScopeChange() {
      const scope = document.querySelector('input[name="balScope"]:checked').value;
      document.getElementById('balRangeRow').style.display = scope === 'range' ? 'flex' : 'none';
      document.getElementById('balSingleRow').style.display = scope === 'single' ? 'block' : 'none';
    }

    function selectFleetCategory(cat) {
      selectedFleetCat = cat;
      document.getElementById('btnModeMult').classList.toggle('active', cat === 'multiplier');
      document.getElementById('btnModeEq').classList.toggle('active', cat === 'equity');
      document.getElementById('btnModeBal').classList.toggle('active', cat === 'balance');
      const btnLeave = document.getElementById('btnModeLeave');
      if (btnLeave) btnLeave.classList.toggle('active', cat === 'leave');

      const multInputSec = document.getElementById('multiplierSection');
      const leaveNotice = document.getElementById('leaveMasterNotice');
      const btnApply = document.getElementById('btnApplyCat');

      if (cat === 'multiplier') {
        multInputSec.style.display = 'block';
        multInputSec.style.opacity = '1';
        multInputSec.style.pointerEvents = 'auto';
        if (leaveNotice) leaveNotice.style.display = 'none';
        if (btnApply) btnApply.innerText = '🚀 Apply Category Configuration to Followers';
        document.getElementById('catActiveBadge').innerText = `MULTIPLIER (${document.getElementById('fleetMultiplierInput').value}x)`;
      } else if (cat === 'equity') {
        multInputSec.style.display = 'block';
        multInputSec.style.opacity = '0.4';
        multInputSec.style.pointerEvents = 'none';
        if (leaveNotice) leaveNotice.style.display = 'none';
        if (btnApply) btnApply.innerText = '🚀 Apply Equity Based Configuration';
        document.getElementById('catActiveBadge').innerText = 'EQUITY BASED (PROPORTIONAL)';
      } else if (cat === 'balance') {
        multInputSec.style.display = 'block';
        multInputSec.style.opacity = '0.4';
        multInputSec.style.pointerEvents = 'none';
        if (leaveNotice) leaveNotice.style.display = 'none';
        if (btnApply) btnApply.innerText = '🚀 Apply Balance Based Configuration';
        document.getElementById('catActiveBadge').innerText = 'BALANCE BASED (PROPORTIONAL)';
      } else if (cat === 'leave') {
        multInputSec.style.display = 'none';
        if (leaveNotice) leaveNotice.style.display = 'block';
        if (btnApply) btnApply.innerText = '🚪 Execute Leave Master for Followers';
        document.getElementById('catActiveBadge').innerText = 'LEAVE MASTER (UNFOLLOW)';
      }
    }

    function setPresetMult(val) {
      document.getElementById('fleetMultiplierInput').value = Number(val).toFixed(1);
      document.querySelectorAll('#multiplierSection .preset-pill').forEach(p => {
        p.classList.toggle('active', p.innerText === `${val}x` || p.innerText === `${val.toFixed(1)}x`);
      });
      if (selectedFleetCat === 'multiplier') {
        document.getElementById('catActiveBadge').innerText = `MULTIPLIER (${val.toFixed(1)}x)`;
      }
    }

    function setPresetBal(val) {
      document.getElementById('fleetBalanceInput').value = val;
      document.querySelectorAll('#tabContentFleetManager .preset-pill').forEach(p => {
        if (p.innerText.startsWith('$')) {
          const m = val >= 1000000 ? `$${val / 1000000}M` : `$${val}`;
          p.classList.toggle('active', p.innerText === m);
        }
      });
    }

    function appendFleetLog(msg, type = 'info') {
      const log = document.getElementById('fleetActivityLog');
      if (!log) return;
      const time = new Date().toLocaleTimeString();
      const color = type === 'success' ? '#34d399' : (type === 'error' ? '#f87171' : (type === 'warn' ? '#facc15' : '#60a5fa'));
      const div = document.createElement('div');
      div.style.marginBottom = '4px';
      div.innerHTML = `<span style="color: var(--text-dim);">[${time}]</span> <span style="color: ${color}; font-weight: 600;">${msg}</span>`;
      log.prepend(div);
    }

    function clearFleetLog() {
      const log = document.getElementById('fleetActivityLog');
      if (log) log.innerHTML = '<div style="color: var(--text-dim);">[SYSTEM] Log cleared. Ready for next action.</div>';
    }

    // --- Master MAM Profit Share & Settings (Decided by Master) ---
    async function saveMasterMAMSettings() {
      const btn = document.getElementById('btnSaveMasterShare');
      const statusBox = document.getElementById('masterShareStatusBox');
      const sharePct = parseFloat(document.getElementById('masterShareInput').value) || 50.0;
      const dispName = document.getElementById('masterDisplayNameInput').value.trim() || 'mammaster';

      btn.disabled = true;
      btn.innerText = "⏳ Saving Master Share to MAM...";
      statusBox.style.display = 'block';
      statusBox.style.color = '#c084fc';
      statusBox.innerText = `Submitting Master MAM settings (Name: ${dispName}, Share: ${sharePct}%)...`;

      appendFleetLog(`Executing Master MAM Settings update: Master ID=mammaster, Name=${dispName}, Share=${sharePct}% via /mam/master...`, 'info');

      try {
        const payload = {
          master_id: activeMasterId,
          share_percent: sharePct,
          display_name: dispName
        };

        const res = await fetch('/api/manage/master-share', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });

        const data = await res.json();
        if (data.success) {
          statusBox.style.color = '#34d399';
          statusBox.innerText = `✅ Success! Master profit share saved as ${sharePct}% (Display: ${dispName}). Followers joining or updating will adhere to this share.`;
          appendFleetLog(`✅ Master MAM Share Saved: ${sharePct}% set on MAM Master (Flow: Master ID -> MAM -> Settings -> Save).`, 'success');
          const fShareBadge = document.getElementById('followerInheritedShare');
          if (fShareBadge) fShareBadge.innerText = `${sharePct}% (Decided by Master)`;
          const mShareBadge = document.getElementById('currentMasterShareBadge');
          if (mShareBadge) mShareBadge.innerText = `MY SHARE: ${sharePct}%`;
          fetchDashboardData();
        } else {
          statusBox.style.color = '#f87171';
          statusBox.innerText = `❌ Error: ${data.error || 'Failed to update master profit share'}`;
          appendFleetLog(`❌ Master MAM Share Failed: ${data.error || 'Unknown error'}`, 'error');
        }
      } catch (err) {
        statusBox.style.color = '#f87171';
        statusBox.innerText = `❌ Request failed: ${err.message}`;
        appendFleetLog(`❌ Network Error: ${err.message}`, 'error');
      } finally {
        btn.disabled = false;
        btn.innerText = "💾 Save Master Profit Share to MAM Settings";
      }
    }

    function setMasterPresetShare(val) {
      document.getElementById('masterShareInput').value = val;
      document.querySelectorAll('#masterSharePresets .preset-pill').forEach(p => {
        p.classList.toggle('active', p.innerText === `${val}%`);
      });
    }

    async function applyFleetBulkFollow() {
      const btn = document.getElementById('btnBulkFollow');
      const statusBox = document.getElementById('catStatusBox');
      const scope = document.querySelector('input[name="catScope"]:checked').value;
      const start = parseInt(document.getElementById('catStartIdx').value) || 1;
      const end = parseInt(document.getElementById('catEndIdx').value) || 100;
      const singleEmail = document.getElementById('catSingleSelect').value;

      btn.disabled = true;
      btn.innerText = "⏳ Following Master in Equity Mode...";
      statusBox.style.display = 'block';
      statusBox.style.color = '#60a5fa';
      statusBox.innerText = `Submitting bulk follow (Equity mode) to ${scope} followers...`;

      appendFleetLog(`Executing Bulk Follow: Master=${activeMasterId.toUpperCase()}, Category=EQUITY, Target=${scope.toUpperCase()}...`, 'info');

      try {
        const payload = {
          target_type: scope,
          start: start,
          end: end,
          single_email: singleEmail,
          category: 'equity',
          multiplier: 1.0
        };

        const res = await fetch('/api/manage/follow', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });

        const data = await res.json();
        if (data.success) {
          statusBox.style.color = '#34d399';
          statusBox.innerText = `✅ Success! ${data.success_count}/${data.total_targeted} followers are now following Master in EQUITY mode.`;
          appendFleetLog(`✅ Bulk Follow Completed: ${data.success_count}/${data.total_targeted} accounts now following Master in EQUITY mode.`, 'success');
          fetchDashboardData();
        } else {
          statusBox.style.color = '#f87171';
          statusBox.innerText = `❌ Error: ${data.error || 'Failed to follow master'}`;
          appendFleetLog(`❌ Bulk Follow Failed: ${data.error || 'Unknown error'}`, 'error');
        }
      } catch (err) {
        statusBox.style.color = '#f87171';
        statusBox.innerText = `❌ Request failed: ${err.message}`;
        appendFleetLog(`❌ Network Error: ${err.message}`, 'error');
      } finally {
        btn.disabled = false;
        btn.innerText = "👥 Bulk Follow Master (Default Equity)";
      }
    }

    function copyChromeSyncSnippet() {
      const broker = selectedFleetBroker || 'real';
      const code = `const f = document.querySelector('iframe'); const uid = f ? f.contentWindow.__IFRAME_CONFIG__?.user_id : ''; if(f && uid) { f.contentWindow.localStorage.setItem('selectedBrokers:' + uid, JSON.stringify(['${broker}'])); f.contentWindow.location.reload(); }`;
      navigator.clipboard.writeText(code).then(() => {
        alert(`Copied Chrome Sync Snippet for [${broker}]! Paste into Chrome DevTools Console (F12) while on https://lpadmin.blackfx.com/dashboard to immediately tick the box.`);
      });
    }

    async function applyFleetCategory() {
      if (selectedFleetCat === 'leave') {
        await applyFleetUnfollow();
        return;
      }

      const btn = document.getElementById('btnApplyCat');
      const statusBox = document.getElementById('catStatusBox');
      const scope = document.querySelector('input[name="catScope"]:checked').value;
      const start = parseInt(document.getElementById('catStartIdx').value) || 1;
      const end = parseInt(document.getElementById('catEndIdx').value) || 100;
      const singleEmail = document.getElementById('catSingleSelect').value;
      const multiplier = parseFloat(document.getElementById('fleetMultiplierInput').value) || 2.0;

      btn.disabled = true;
      btn.innerText = "⏳ Applying Category Switch in Parallel...";
      statusBox.style.display = 'block';
      statusBox.style.color = '#60a5fa';
      statusBox.innerText = `Submitting category change (${selectedFleetCat}, mult: ${multiplier}x) to ${scope} followers...`;

      appendFleetLog(`Executing category change: Category=${selectedFleetCat.toUpperCase()}, Multiplier=${multiplier}x, Target=${scope.toUpperCase()}...`, 'info');

      try {
        const payload = {
          master_id: activeMasterId,
          target_type: scope,
          start: start,
          end: end,
          single_email: singleEmail,
          category: selectedFleetCat,
          multiplier: multiplier
        };

        const res = await fetch('/api/manage/category', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });

        const data = await res.json();
        if (data.success) {
          statusBox.style.color = '#34d399';
          statusBox.innerText = `✅ Success! Updated ${data.success_count}/${data.total_targeted} followers to ${selectedFleetCat.toUpperCase()} mode.`;
          appendFleetLog(`✅ Category Switch Completed: ${data.success_count}/${data.total_targeted} accounts updated to ${selectedFleetCat} (mult: ${multiplier}x).`, 'success');
          fetchDashboardData();
        } else {
          statusBox.style.color = '#f87171';
          statusBox.innerText = `❌ Error: ${data.error || 'Failed to update category'}`;
          appendFleetLog(`❌ Category Switch Failed: ${data.error || 'Unknown error'}`, 'error');
        }
      } catch (err) {
        statusBox.style.color = '#f87171';
        statusBox.innerText = `❌ Request failed: ${err.message}`;
        appendFleetLog(`❌ Network Error: ${err.message}`, 'error');
      } finally {
        btn.disabled = false;
        btn.innerText = "🚀 Apply Category Configuration to Followers";
      }
    }

    async function applyFleetBalance() {
      const btn = document.getElementById('btnApplyBal');
      const statusBox = document.getElementById('balStatusBox');
      const scope = document.querySelector('input[name="balScope"]:checked').value;
      const start = parseInt(document.getElementById('balStartIdx').value) || 1;
      const end = parseInt(document.getElementById('balEndIdx').value) || 100;
      const singleEmail = document.getElementById('balSingleSelect').value;
      const balance = parseFloat(document.getElementById('fleetBalanceInput').value) || 10000000.0;

      btn.disabled = true;
      btn.innerText = "⏳ Updating Balances via Admin API in Parallel...";
      statusBox.style.display = 'block';
      statusBox.style.color = '#34d399';
      statusBox.innerText = `Connecting to Admin API to inject ${fmtMoney(balance)} across ${scope} followers...`;

      appendFleetLog(`Executing Admin balance update: Amount=${fmtMoney(balance)}, Target=${scope.toUpperCase()}...`, 'info');

      try {
        const payload = {
          target_type: scope,
          start: start,
          end: end,
          single_email: singleEmail,
          balance: balance,
          instance: selectedBalEnv
        };

        const res = await fetch('/api/manage/balance', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });

        const data = await res.json();
        if (data.success) {
          statusBox.style.color = '#34d399';
          statusBox.innerText = `✅ Success! Updated balance for ${data.success_count}/${data.total_targeted} followers to ${fmtMoney(balance)}.`;
          appendFleetLog(`✅ Balance Update Completed: ${data.success_count}/${data.total_targeted} accounts updated to ${fmtMoney(balance)} via Admin API.`, 'success');
          fetchDashboardData();
        } else {
          statusBox.style.color = '#f87171';
          statusBox.innerText = `❌ Error: ${data.error || 'Failed to update balance'}`;
          appendFleetLog(`❌ Balance Update Failed: ${data.error || 'Unknown error'}`, 'error');
        }
      } catch (err) {
        statusBox.style.color = '#f87171';
        statusBox.innerText = `❌ Request failed: ${err.message}`;
        appendFleetLog(`❌ Network Error: ${err.message}`, 'error');
      } finally {
        btn.disabled = false;
        btn.innerText = "💸 Set Account Balances via Admin API";
      }
    }

    // --- Fleet controls that the markup references (environment, broker, book, balance environment) ---
    let selectedBalEnv = 'paper';
    let selectedFleetBroker = 'real';
    let selectedFleetBook = 'a';

    function syncEnvButtons(env) {
      document.getElementById('envBtnPaper').classList.toggle('active', env === 'paper');
      document.getElementById('envBtnPaperNet').classList.toggle('active', env === 'paper-net');
      document.getElementById('envBtnReal').classList.toggle('active', env === 'real');
      document.getElementById('envBtnRealNet').classList.toggle('active', env === 'real-net');
    }
    const INSTANCE_LABELS = { 'paper': 'Paper (Hedging)', 'paper-net': 'Paper (Netting)', 'real': 'Real (Hedging)', 'real-net': 'Real (Netting)' };
    const instLabel = (i) => INSTANCE_LABELS[i] || String(i || '').toUpperCase();
    const instBadgeHtml = (i) => (String(i).startsWith('real') ? (i === 'real-net' ? '🔷 ' : '💎 ') : '📄 ') + instLabel(i).toUpperCase();
    const instBadgeClass = (i) => String(i).startsWith('real') ? 'badge badge-env-real' : 'badge badge-env-paper';

    async function switchEnvironment(env) {
      syncEnvButtons(env);
      try {
        const res = await fetch('/api/manage/environment', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ instance: env })
        });
        const data = await res.json();
        if (data.success) {
          appendFleetLog(`Environment switched to ${instLabel(env)}`, 'success');
          setTimeout(fetchDashboardData, 600);
        } else {
          appendFleetLog(`Environment switch failed: ${data.error || 'unknown error'}`, 'error');
        }
      } catch (e) {
        appendFleetLog(`Environment switch failed: ${e.message}`, 'error');
      }
    }

    function selectBalEnv(env) {
      selectedBalEnv = env;
      document.getElementById('balEnvPaper').classList.toggle('active', env === 'paper');
      document.getElementById('balEnvReal').classList.toggle('active', env === 'real');
      document.getElementById('balEnvRealNet').classList.toggle('active', env === 'real-net');
      document.getElementById('balEnvBoth').classList.toggle('active', env === 'both');
    }

    function _scopeToggle(prefix, name) {
      const scope = document.querySelector(`input[name="${name}"]:checked`).value;
      document.getElementById(`${prefix}RangeRow`).style.display = scope === 'range' ? 'flex' : 'none';
      document.getElementById(`${prefix}SingleRow`).style.display = scope === 'single' ? 'block' : 'none';
    }
    function onBrokerScopeChange() { _scopeToggle('broker', 'brokerScope'); }
    function onBookScopeChange() { _scopeToggle('book', 'bookScope'); }

    function populateBrokerBookDropdowns() {
      const followers = currentData.followers || [];
      ['brokerSingleSelect', 'bookSingleSelect'].forEach(id => {
        const sel = document.getElementById(id);
        if (!sel || sel.options.length === followers.length) return;
        const cur = sel.value;
        sel.innerHTML = followers.map(f => `<option value="${f.email}">${f.email} (${(f.book || '?').toUpperCase()}-book, ${f.broker_setting || '?'})</option>`).join('');
        if (cur) sel.value = cur;
      });
      // First load: preselect the broker setting the followers are actually on (all on one instance), once only.
      if (!window._fleetBrokerInit && followers.length) {
        window._fleetBrokerInit = true;
        const modes = new Set(followers.map(f => f.broker_setting).filter(Boolean));
        if (modes.size === 1) selectFleetBroker([...modes][0]);
      }
    }

    // --- Broker Settings Controller (Trades Module Settings) ---
    const BROKER_PROPS = {
      'paper': { id: 'paper', name: 'Paper (Hedging)', moneyTag: 'PRACTICE ACCOUNT', tagBg: 'rgba(59, 130, 246, 0.2)', tagColor: '#60a5fa', desc: 'This is a sandbox practice account for simulation and testing.' },
      'real': { id: 'real', name: 'Real (Hedging)', moneyTag: 'REAL MONEY', tagBg: 'rgba(245, 158, 11, 0.2)', tagColor: '#f59e0b', desc: 'This is a real-money account. Its balance changes by deposit or an admin adjustment.' },
      'paper-net': { id: 'paper-net', name: 'Paper (Netting)', moneyTag: 'PRACTICE ACCOUNT', tagBg: 'rgba(59, 130, 246, 0.2)', tagColor: '#60a5fa', desc: 'This is a simulated netting practice account.' },
      'real-net': { id: 'real-net', name: 'Real (Netting)', moneyTag: 'REAL MONEY', tagBg: 'rgba(245, 158, 11, 0.2)', tagColor: '#f59e0b', desc: 'This is a live real-money netting account funded via Admin API.' }
    };

    function selectFleetBrokerTab(b) {
      selectedFleetBroker = b;
      ['paper', 'real', 'paper-net', 'real-net'].forEach(key => {
        const tabEl = document.getElementById('tabBroker' + key.split('-').map(s => s.charAt(0).toUpperCase() + s.slice(1)).join(''));
        if (tabEl) {
          tabEl.classList.toggle('active', key === b);
          tabEl.style.color = key === b ? '#60a5fa' : '#94a3b8';
          tabEl.style.fontWeight = key === b ? '700' : '600';
          tabEl.style.borderBottom = key === b ? '2px solid #3b82f6' : '2px solid transparent';
        }
      });

      const p = BROKER_PROPS[b] || BROKER_PROPS['real'];
      document.getElementById('brokerIdLabel').innerText = p.id;
      document.getElementById('lblEnableBroker').innerText = `Enable ${p.name}`;
      document.getElementById('brokerMoneyTag').innerText = p.moneyTag;
      document.getElementById('brokerMoneyTag').style.background = p.tagBg;
      document.getElementById('brokerMoneyTag').style.color = p.tagColor;
      document.getElementById('brokerBalanceDesc').innerText = p.desc;

      const activeBadge = document.getElementById('brokerActiveBadge');
      if (activeBadge) {
        activeBadge.innerText = `${p.name.toUpperCase()} ● CONNECTED`;
        activeBadge.className = b.startsWith('real') ? 'badge badge-env-real' : 'badge badge-env-paper';
      }

      // Update sample balances based on group cache
      const followers = currentData.followers || [];
      const f1 = followers[0] || {};
      let bal = 1000.00;
      if (b === 'paper') bal = f1.paper_balance || 10000000;
      else if (b === 'real') bal = f1.real_balance || 1000;
      else bal = 1000;

      document.getElementById('brokerBalVal').innerText = Number(bal).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
      document.getElementById('brokerEqVal').innerText = Number(bal).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
      document.getElementById('brokerFreeVal').innerText = Number(bal).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
      document.getElementById('brokerUsedVal').innerText = '0.00';
      const snip = document.getElementById('chromeSyncSnippet');
      if (snip) {
        snip.innerText = `const f = document.querySelector('iframe'); const uid = f ? f.contentWindow.__IFRAME_CONFIG__?.user_id : ''; if(f && uid) { f.contentWindow.localStorage.setItem('selectedBrokers:' + uid, JSON.stringify(['${b}'])); f.contentWindow.location.reload(); }`;
      }

    }

    function onBrokerCheckboxToggle() {
      const isChecked = document.getElementById('chkEnableBroker').checked;
      applyFleetBrokerToggle(isChecked ? 'enable' : 'disable');
    }

    async function applyFleetBrokerToggle(action) {
      const p = BROKER_PROPS[selectedFleetBroker] || BROKER_PROPS['real'];
      const payload = Object.assign(_fleetScopePayload('broker', 'brokerScope'), {
        target_broker: selectedFleetBroker,
        action: action,
        category: selectedFleetCat === 'leave' ? 'multiplier' : selectedFleetCat,
        multiplier: parseFloat(document.getElementById('fleetMultiplierInput').value) || 2.0
      });

      const verb = action === 'enable' ? 'Enable' : 'Disable';
      if (payload.target_type === 'all' && !confirm(`${verb} broker setting ${p.name} for ALL 100 followers?`)) {
        // Revert checkbox state
        document.getElementById('chkEnableBroker').checked = (action !== 'enable');
        return;
      }

      const btnId = action === 'enable' ? 'btnEnableBrokerFleet' : 'btnDisableBrokerFleet';
      const idleText = action === 'enable' ? '🟢 Enable Broker Setting for Followers' : '🔴 Disable Broker Setting for Followers';

      await _applyFleet(
        btnId,
        'brokerStatusBox',
        `⏳ ${verb}ing ${p.name}...`,
        idleText,
        '/api/manage/broker-setting',
        payload,
        `Broker setting → ${p.name} ${action.toUpperCase()}D`,
        `Failed to ${action} broker setting`
      );

      // Sync checkbox and status text
      const chk = document.getElementById('chkEnableBroker');
      const indText = document.getElementById('brokerConnectedText');
      const indDot = document.getElementById('brokerConnectedDot');
      if (action === 'enable') {
        chk.checked = true;
        if (indText) indText.innerText = 'connected';
        if (indDot) indDot.style.background = '#10b981';
      } else {
        chk.checked = false;
        if (indText) indText.innerText = 'disconnected';
        if (indDot) indDot.style.background = '#64748b';
      }
    }

    async function applyFleetUnfollow() {
      const payload = _fleetScopePayload('cat', 'catScope');
      if (payload.target_type === 'all' && !confirm('Are you sure you want ALL 100 followers to LEAVE the MAM master across all instances?')) return;

      await _applyFleet(
        'btnApplyUnfollow',
        'catStatusBox',
        '⏳ Unfollowing Fleet...',
        '🚪 Leave Master',
        '/api/manage/unfollow',
        payload,
        'Leave Master (Unfollowed)',
        'Failed to unfollow from master'
      );
    }

    function selectFleetBroker(b) {
      selectFleetBrokerTab(b);
    }

    function selectFleetBook(b) {
      selectedFleetBook = b;
      document.getElementById('btnBookA').classList.toggle('active', b === 'a');
      document.getElementById('btnBookB').classList.toggle('active', b === 'b');
    }

    function _fleetScopePayload(prefix, name) {
      return {
        target_type: document.querySelector(`input[name="${name}"]:checked`).value,
        start: parseInt(document.getElementById(`${prefix}StartIdx`).value) || 1,
        end: parseInt(document.getElementById(`${prefix}EndIdx`).value) || 100,
        single_email: document.getElementById(`${prefix}SingleSelect`).value
      };
    }

    async function _applyFleet(btnId, statusId, busyText, idleText, url, payload, okText, failText) {
      const btn = document.getElementById(btnId);
      const statusBox = document.getElementById(statusId);
      if (btn) {
        btn.disabled = true;
        btn.innerText = busyText;
      }
      statusBox.style.display = 'block';
      statusBox.style.color = '#60a5fa';
      statusBox.innerText = 'Submitting...';
      try {
        const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        const data = await res.json();
        if (data.success) {
          statusBox.style.color = data.fail_count ? '#facc15' : '#34d399';
          statusBox.innerText = `${data.fail_count ? '⚠️' : '✅'} ${okText}: ${data.success_count}/${data.total_targeted} accounts updated` + (data.fail_count ? `, ${data.fail_count} failed.` : '.');
          appendFleetLog(`${okText}: ${data.success_count}/${data.total_targeted} accounts updated.`, data.fail_count ? 'warn' : 'success');
          fetchDashboardData();
        } else {
          statusBox.style.color = '#f87171';
          statusBox.innerText = `❌ Error: ${data.error || failText}`;
          appendFleetLog(`❌ ${failText}: ${data.error || 'Unknown error'}`, 'error');
        }
      } catch (e) {
        statusBox.style.color = '#f87171';
        statusBox.innerText = `❌ Request failed: ${e.message}`;
        appendFleetLog(`❌ Network Error: ${e.message}`, 'error');
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.innerText = idleText;
        }
      }
    }

    async function applyFleetBook() {
      const payload = Object.assign(_fleetScopePayload('book', 'bookScope'), { book: selectedFleetBook });
      if (payload.target_type === 'all' && !confirm(`Convert ALL followers to ${selectedFleetBook.toUpperCase()}-Book? This changes where REAL orders are executed.`)) return;
      await _applyFleet('btnApplyBook', 'bookStatusBox', '⏳ Converting Book...', '🔄 Convert Fleet Book via Admin API',
        '/api/manage/book', payload, `Book → ${selectedFleetBook.toUpperCase()}-Book`, 'Book conversion failed');
    }

    async function toggleFollowerBook(email, targetBook) {
      try {
        const res = await fetch('/api/manage/book', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ target_type: 'single', single_email: email, book: targetBook })
        });
        const data = await res.json();
        if (data.success && data.success_count > 0) {
          appendFleetLog(`${email} converted to ${targetBook.toUpperCase()}-Book via Admin API`, 'success');
        } else {
          appendFleetLog(`❌ ${email} book change failed: ${data.error || 'unknown error'}`, 'error');
          alert(`Book change failed: ${data.error || 'unknown error'}`);
        }
        fetchDashboardData();
      } catch (e) {
        appendFleetLog(`❌ ${email} book change failed: ${e.message}`, 'error');
      }
    }

    // --- Quick Manage Modal for Individual Follower ---
    let quickManageTargetEmail = null;

    function openQuickManageModal(email) {
      quickManageTargetEmail = email;
      const followers = currentData.followers || [];
      const f = followers.find(x => x.email === email);
      if (!f) return;

      document.getElementById('quickManageEmail').innerText = `⚙️ ${f.email}`;
      document.getElementById('quickManageSub').innerText = `Member ID: ${f.member_id} | Book: ${String(f.book || 'B').toUpperCase()}-Book | Broker: ${instLabel(f.broker_setting || 'paper')}`;
      document.getElementById('qmCategory').value = f.method || 'multiplier';
      document.getElementById('qmMultiplier').value = f.multiplier || 2.0;

      const fBook = (f.book || 'b').toLowerCase();
      document.getElementById('qmCurrentBookBadge').innerText = fBook === 'a' ? '📙 A-BOOK' : '📘 B-BOOK';
      document.getElementById('qmCurrentBookBadge').className = fBook === 'a' ? 'badge badge-gold' : 'badge badge-mult';

      const fBroker = (f.broker_setting || 'paper').toLowerCase();
      document.getElementById('qmCurrentBrokerBadge').innerText = instBadgeHtml(fBroker);
      document.getElementById('qmCurrentBrokerBadge').className = instBadgeClass(fBroker);

      document.getElementById('qmPaperBalance').value = f.paper_balance !== undefined ? f.paper_balance : f.balance;
      document.getElementById('qmRealBalance').value = f.real_balance || 10000000;
      onQmCategoryChange();

      const statusBox = document.getElementById('qmStatusBox');
      statusBox.style.display = 'none';

      document.getElementById('quickManageModal').style.display = 'flex';
    }

    function onQmCategoryChange() {
      const cat = document.getElementById('qmCategory').value;
      document.getElementById('qmMultiplierRow').style.display = cat === 'multiplier' ? 'block' : 'none';
    }

    async function quickManageLeaveMaster() {
      if (!quickManageTargetEmail) return;
      const statusBox = document.getElementById('qmStatusBox');
      statusBox.style.display = 'block';
      statusBox.style.color = '#f87171';
      statusBox.innerText = `Unfollowing ${quickManageTargetEmail} from master across all instances...`;

      try {
        const res = await fetch('/api/manage/unfollow', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            target_type: 'single',
            single_email: quickManageTargetEmail
          })
        });
        const data = await res.json();
        if (data.success && data.success_count > 0) {
          statusBox.style.color = '#34d399';
          statusBox.innerText = `✅ ${quickManageTargetEmail} left the master cleanly!`;
          appendFleetLog(`Quick Edit: ${quickManageTargetEmail} left the MAM master (unfollowed)`, 'success');
          fetchDashboardData();
        } else {
          statusBox.style.color = '#f87171';
          statusBox.innerText = `❌ Error: ${data.error || 'Failed to leave master'}`;
        }
      } catch (e) {
        statusBox.style.color = '#f87171';
        statusBox.innerText = `❌ Error: ${e.message}`;
      }
    }

    async function quickManageToggleBroker(targetBroker, action) {
      if (!quickManageTargetEmail) return;
      const statusBox = document.getElementById('qmStatusBox');
      statusBox.style.display = 'block';
      statusBox.style.color = '#60a5fa';
      statusBox.innerText = `${action === 'enable' ? 'Enabling' : 'Disabling'} ${instLabel(targetBroker)} for ${quickManageTargetEmail}...`;

      try {
        const res = await fetch('/api/manage/broker-setting', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            target_type: 'single',
            single_email: quickManageTargetEmail,
            target_broker: targetBroker,
            action: action,
            category: document.getElementById('qmCategory').value || 'multiplier',
            multiplier: parseFloat(document.getElementById('qmMultiplier').value) || 2.0
          })
        });
        const data = await res.json();
        if (data.success && data.success_count > 0) {
          statusBox.style.color = '#34d399';
          statusBox.innerText = `✅ ${instLabel(targetBroker)} ${action.toUpperCase()}D for ${quickManageTargetEmail}!`;
          document.getElementById('qmCurrentBrokerBadge').innerText = instBadgeHtml(targetBroker);
          document.getElementById('qmCurrentBrokerBadge').className = instBadgeClass(targetBroker);
          appendFleetLog(`Quick Edit: ${quickManageTargetEmail} broker setting ${instLabel(targetBroker)} ${action.toUpperCase()}D`, 'success');
          fetchDashboardData();
        } else {
          statusBox.style.color = '#f87171';
          statusBox.innerText = `❌ Error: ${data.error || 'Failed to update broker setting'}`;
        }
      } catch (e) {
        statusBox.style.color = '#f87171';
        statusBox.innerText = `❌ Error: ${e.message}`;
      }
    }

    async function saveQuickManageCategory() {
      if (!quickManageTargetEmail) return;
      const statusBox = document.getElementById('qmStatusBox');
      const cat = document.getElementById('qmCategory').value;
      const mult = parseFloat(document.getElementById('qmMultiplier').value) || 2.0;

      statusBox.style.display = 'block';
      statusBox.style.color = '#60a5fa';
      statusBox.innerText = `Saving category ${cat} (${mult}x)...`;

      try {
        const payload = {
          master_id: activeMasterId,
          target_type: 'single',
          single_email: quickManageTargetEmail,
          category: cat,
          multiplier: mult
        };
        const res = await fetch('/api/manage/category', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success && data.success_count > 0) {
          statusBox.style.color = '#34d399';
          statusBox.innerText = `✅ Updated ${quickManageTargetEmail} to ${cat} (${mult}x)!`;
          appendFleetLog(`Quick Edit: ${quickManageTargetEmail} category switched to ${cat} (${mult}x)`, 'success');
          fetchDashboardData();
        } else {
          statusBox.style.color = '#f87171';
          statusBox.innerText = `❌ Error: ${data.error || 'Failed to update category'}`;
        }
      } catch (e) {
        statusBox.style.color = '#f87171';
        statusBox.innerText = `❌ Error: ${e.message}`;
      }
    }

    async function saveQuickManageBook(targetBook) {
      if (!quickManageTargetEmail) return;
      const statusBox = document.getElementById('qmStatusBox');
      statusBox.style.display = 'block';
      statusBox.style.color = '#fbbf24';
      statusBox.innerText = `Converting to ${targetBook.toUpperCase()}-Book via Admin API...`;

      try {
        const res = await fetch('/api/manage/book', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            target_type: 'single',
            single_email: quickManageTargetEmail,
            book: targetBook
          })
        });
        const data = await res.json();
        if (data.success && data.success_count > 0) {
          statusBox.style.color = '#34d399';
          statusBox.innerText = `✅ Converted to ${targetBook.toUpperCase()}-Book!`;
          document.getElementById('qmCurrentBookBadge').innerText = targetBook === 'a' ? '📙 A-BOOK' : '📘 B-BOOK';
          document.getElementById('qmCurrentBookBadge').className = targetBook === 'a' ? 'badge badge-gold' : 'badge badge-mult';
          appendFleetLog(`Quick Edit: ${quickManageTargetEmail} converted to ${targetBook.toUpperCase()}-Book via Admin API`, 'success');
          fetchDashboardData();
        } else {
          statusBox.style.color = '#f87171';
          statusBox.innerText = `❌ Error: ${data.error || 'Failed to convert book'}`;
        }
      } catch (e) {
        statusBox.style.color = '#f87171';
        statusBox.innerText = `❌ Error: ${e.message}`;
      }
    }

    async function saveQuickManageBroker(targetBroker) {
      if (!quickManageTargetEmail) return;
      const statusBox = document.getElementById('qmStatusBox');
      statusBox.style.display = 'block';
      statusBox.style.color = '#f472b6';
      statusBox.innerText = `Unfollowing, then following on ${instLabel(targetBroker)}...`;

      try {
        const res = await fetch('/api/manage/broker-setting', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            target_type: 'single',
            single_email: quickManageTargetEmail,
            target_broker: targetBroker,
            category: document.getElementById('qmCategory').value,
            multiplier: parseFloat(document.getElementById('qmMultiplier').value) || 2.0
          })
        });
        const data = await res.json();
        if (data.success && data.success_count > 0) {
          statusBox.style.color = '#34d399';
          statusBox.innerText = `✅ Switched to ${instLabel(targetBroker)}!`;
          document.getElementById('qmCurrentBrokerBadge').innerText = instBadgeHtml(targetBroker);
          document.getElementById('qmCurrentBrokerBadge').className = instBadgeClass(targetBroker);
          appendFleetLog(`Quick Edit: ${quickManageTargetEmail} broker setting switched to ${instLabel(targetBroker)}`, 'success');
          fetchDashboardData();
        } else {
          statusBox.style.color = '#f87171';
          statusBox.innerText = `❌ Error: ${data.error || 'Failed to update broker setting'}`;
        }
      } catch (e) {
        statusBox.style.color = '#f87171';
        statusBox.innerText = `❌ Error: ${e.message}`;
      }
    }

    async function saveQuickManageBalance(instance) {
      if (!quickManageTargetEmail) return;
      const statusBox = document.getElementById('qmStatusBox');
      const inputEl = instance === 'real' ? document.getElementById('qmRealBalance') : document.getElementById('qmPaperBalance');
      const bal = parseFloat(inputEl.value) || 10000000;

      statusBox.style.display = 'block';
      statusBox.style.color = instance === 'real' ? '#f472b6' : '#c084fc';
      statusBox.innerText = `Setting ${instance.toUpperCase()} balance to ${fmtMoney(bal)} via Admin API...`;

      try {
        const payload = {
          target_type: 'single',
          single_email: quickManageTargetEmail,
          balance: bal,
          instance: instance
        };
        const res = await fetch('/api/manage/balance', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success && data.success_count > 0) {
          statusBox.style.color = '#34d399';
          statusBox.innerText = `✅ ${instance.toUpperCase()} balance for ${quickManageTargetEmail} set to ${fmtMoney(bal)}!`;
          appendFleetLog(`Quick Edit: ${quickManageTargetEmail} ${instance.toUpperCase()} balance set to ${fmtMoney(bal)} via Admin API`, 'success');
          fetchDashboardData();
        } else {
          statusBox.style.color = '#f87171';
          statusBox.innerText = `❌ Error: ${data.error || 'Failed to update balance'}`;
        }
      } catch (e) {
        statusBox.style.color = '#f87171';
        statusBox.innerText = `❌ Error: ${e.message}`;
      }
    }

        // Initialize
    fetchDashboardData();
    startAutoSync();
  </script>
</body>
</html>
"""



# ----------------------------------------------------------------------------
# Test-operations add-on (Test Runner + Evidence Reports tabs)
# ----------------------------------------------------------------------------
from urllib.parse import urlparse, parse_qs, unquote  # noqa: E402
from dashboard import testops  # noqa: E402
from config.settings import DASHBOARD_TOKEN  # noqa: E402
import hmac  # noqa: E402


def build_dashboard_page() -> str:
    """Terminal page with the Test Runner / Reports panel spliced in ahead of the main script."""
    panel_file = BASE_DIR / "dashboard" / "mam_testops_panel.html"
    try:
        panel = panel_file.read_text(encoding="utf-8")
    except OSError:
        return ENTERPRISE_DASHBOARD_HTML
    marker = "  <script>" + chr(10) + "    let activeTab"
    if marker not in ENTERPRISE_DASHBOARD_HTML:
        return ENTERPRISE_DASHBOARD_HTML
    return ENTERPRISE_DASHBOARD_HTML.replace(marker, panel + chr(10) + marker, 1)


class DashboardHTTPRequestHandler(BaseHTTPRequestHandler):
    data_manager: MultiMasterDashboardManager = None

    def log_message(self, format, *args):
        pass

    def _send_json(self, payload, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def _authorized(self, parsed_query) -> bool:
        """Optional access token: enforced only when DASHBOARD_TOKEN is set in .env."""
        if not DASHBOARD_TOKEN:
            return True
        cookie = ""
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "bt_dash":
                cookie = v
        supplied = cookie or self.headers.get("X-Dashboard-Token") or (parsed_query.get("token") or [""])[0]
        return hmac.compare_digest(supplied, DASHBOARD_TOKEN)

    def _testops_get(self, path, q):
        """Returns True if the path was a test-operations route (and has been answered)."""
        if path == "/api/config":
            res = testops.get_config()
        elif path == "/api/suites":
            res = testops.get_suites()
        elif path == "/api/health":
            res = testops.get_health(offline=q.get("offline") == ["1"], refresh=q.get("refresh") == ["1"])
        elif path == "/api/status":
            res = testops.get_status()
        elif path == "/api/logs":
            res = testops.get_logs()
        elif path == "/api/history":
            res = testops.get_history()
        elif path.startswith("/api/history/") and path.endswith("/log"):
            res = testops.get_history_log(unquote(path[len("/api/history/"):-len("/log")]))
        elif path == "/api/summary":
            res = testops.get_summary()
        elif path == "/api/reports":
            res = testops.get_reports()
        elif path.startswith("/api/reports/"):
            res = testops.get_report_content(unquote(path[len("/api/reports/"):]))
        else:
            return False
        self._send_json(*res)
        return True

    def do_GET(self):
        url_parts = self.path.split("?")
        path = url_parts[0]
        query = url_parts[1] if len(url_parts) > 1 else ""
        parsed_q = parse_qs(query)

        if not self._authorized(parsed_q):
            self.send_response(401)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Dashboard is locked. Open /?token=<DASHBOARD_TOKEN>")
            return

        if self._testops_get(path, parsed_q):
            return

        if path in ["/", "/index.html"]:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            if DASHBOARD_TOKEN and (parsed_q.get("token") or [""])[0]:
                self.send_header("Set-Cookie", f"bt_dash={DASHBOARD_TOKEN}; HttpOnly; SameSite=Strict; Path=/")
            self.end_headers()
            self.wfile.write(build_dashboard_page().encode("utf-8"))

        elif path == "/api/data":
            master_param = "mam"
            if "master=" in query:
                for q in query.split("&"):
                    if q.startswith("master="):
                        master_param = q.split("=")[1].strip()

            target_group = self.data_manager.groups.get(master_param, self.data_manager.groups["mam"])

            if "instance=" in query:
                for q in query.split("&"):
                    if q.startswith("instance="):
                        req_inst = q.split("=")[1].strip().lower()
                        if req_inst in ALL_INSTANCES and req_inst != self.data_manager.instance:
                            self.data_manager.handle_environment_switch(req_inst)

            with self.data_manager.lock:
                cache_copy = target_group.cache.copy()
                cache_copy["meta"] = {
                    "last_updated": self.data_manager.last_update_str,
                    "active_master": master_param,
                    "active_environment": self.data_manager.instance,
                    "status": "ERROR" if getattr(target_group, "last_error", None) else "LIVE",
                    "error": getattr(target_group, "last_error", None)
                }
                payload = json.dumps(cache_copy)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(payload.encode("utf-8"))

        elif path == "/api/refresh":
            for g in self.data_manager.groups.values():
                threading.Thread(target=self.data_manager.update_single_group, args=(g,)).start()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"refreshing"}')

        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        url_parts = self.path.split("?")
        path = url_parts[0]

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            payload = {}

        if not self._authorized(parse_qs(url_parts[1] if len(url_parts) > 1 else "")):
            self._send_json({"error": "unauthorized"}, 401)
            return

        if path == "/api/run":
            self._send_json(*testops.run_suite(payload))
            return
        if path == "/api/stop":
            self._send_json(*testops.stop_suite())
            return

        if path == "/api/manage/master-share":
            master_id = payload.get("master_id", "mam")
            share_percent = float(payload.get("share_percent", 50.0))
            display_name = payload.get("display_name", None)

            res = self.data_manager.handle_master_share_change(
                master_id=master_id,
                share_percent=share_percent,
                display_name=display_name
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))

        elif path == "/api/manage/category":
            target_type = payload.get("target_type", "all")
            start = int(payload.get("start", 1))
            end = int(payload.get("end", 100))
            single_email = payload.get("single_email", "")
            category = payload.get("category", "multiplier")
            multiplier = float(payload.get("multiplier", 2.0))
            share_percent = float(payload.get("share_percent", 50.0))

            res = self.data_manager.handle_category_change(
                target_type=target_type,
                start=start,
                end=end,
                single_email=single_email,
                category=category,
                multiplier=multiplier,
                share_percent=share_percent
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))

        elif path == "/api/manage/balance":
            target_type = payload.get("target_type", "all")
            start = int(payload.get("start", 1))
            end = int(payload.get("end", 100))
            single_email = payload.get("single_email", "")
            balance = float(payload.get("balance", 10000000.0))
            instance = payload.get("instance", "paper")

            res = self.data_manager.handle_balance_change(
                target_type=target_type,
                start=start,
                end=end,
                single_email=single_email,
                balance=balance,
                instance=instance
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))

        elif path == "/api/manage/book":
            target_type = payload.get("target_type", "all")
            start = int(payload.get("start", 1))
            end = int(payload.get("end", 100))
            single_email = payload.get("single_email", "")
            book = payload.get("book", "b")

            res = self.data_manager.handle_book_change(
                target_type=target_type,
                start=start,
                end=end,
                single_email=single_email,
                book=book
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))

        elif path == "/api/manage/follow":
            target_type = payload.get("target_type", "all")
            start = int(payload.get("start", 1))
            end = int(payload.get("end", 100))
            single_email = payload.get("single_email", "")
            category = payload.get("category", "equity")
            multiplier = float(payload.get("multiplier", 1.0))

            res = self.data_manager.handle_bulk_follow(
                target_type=target_type,
                start=start,
                end=end,
                single_email=single_email,
                category=category,
                multiplier=multiplier
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))

        elif path == "/api/manage/unfollow":
            target_type = payload.get("target_type", "all")
            start = int(payload.get("start", 1))
            end = int(payload.get("end", 100))
            single_email = payload.get("single_email", "")

            res = self.data_manager.handle_unfollow(
                target_type=target_type,
                start=start,
                end=end,
                single_email=single_email
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))

        elif path == "/api/manage/broker-setting":
            target_type = payload.get("target_type", "all")
            start = int(payload.get("start", 1))
            end = int(payload.get("end", 100))
            single_email = payload.get("single_email", "")
            target_broker = payload.get("target_broker", "real")
            action = payload.get("action", "enable")
            category = payload.get("category", "multiplier")
            multiplier = float(payload.get("multiplier", 2.0))
            share_percent = float(payload.get("share_percent", 50.0))

            res = self.data_manager.handle_broker_setting_change(
                target_type=target_type,
                start=start,
                end=end,
                single_email=single_email,
                target_broker=target_broker,
                action=action,
                category=category,
                multiplier=multiplier,
                share_percent=share_percent
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))

        elif path == "/api/manage/environment":
            instance = payload.get("instance", "paper")
            res = self.data_manager.handle_environment_switch(instance)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))

        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")


def run_dashboard_server(port: int = 8500):
    env = load_env_file(".env")
    url = env.get("URL", DEFAULT_BASE_URL)
    url = re.sub(r"/blackadmin/?$", "", url).rstrip("/")
    password = env.get("FOLLOWERS_PASSWORD", env.get("ADMIN_PASSWORD", DEFAULT_PASSWORD))

    print("\n" + "=" * 85)
    print(" 🚀 BLACKTRADER ENTERPRISE: SOCIAL TRADING UNIFIED DASHBOARD")
    print("=" * 85)
    print(f"[*] Base URL            : {url}")
    print(f"[*] Dashboard URL       : http://localhost:{port}")
    print(f"[*] Active Master       : MAM Master (mammaster@mailinator.com - 100 Followers)")
    print("=" * 85 + "\n")

    manager = MultiMasterDashboardManager(base_url=url, password=password)

    # Start background poller thread (1s real-time live sync)
    t = threading.Thread(target=manager.background_poller, kwargs={"interval": 1}, daemon=True)
    t.start()

    DashboardHTTPRequestHandler.data_manager = manager

    server = ThreadedHTTPServer(("0.0.0.0", port), DashboardHTTPRequestHandler)
    print(f"[+] Enterprise Dashboard Server listening at http://localhost:{port}/")
    print("[+] Press Ctrl+C to stop.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Stopping dashboard...")
        manager.is_running = False
        server.shutdown()


def main():
    parser = argparse.ArgumentParser(description="BlackTrader Social Trading Unified Enterprise Dashboard")
    parser.add_argument("--port", type=int, default=8500, help="Server port (default: 8500)")
    args = parser.parse_args()
    run_dashboard_server(port=args.port)


if __name__ == "__main__":
    main()
