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
from typing import Dict, Any, List, Optional
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
    },
    "copy": {
        "id": "copy",
        "name": "Copy Trading Master",
        "email": "ctmaster@mailinator.com",
        "client_id": "mem_aac4ca423a6925dca7",
        "type": "Copy Trading",
        "follower_prefix": "follower",
        "follower_domain": "mailinator.com",
        "follower_count": 100
    },
    "pamm": {
        "id": "pamm",
        "name": "PAMM Master (Pooled Allocation)",
        "email": "pammmaster@mailinator.com",
        "client_id": "mem_a172ed2a58a43fbde1",
        "type": "PAMM",
        "follower_prefix": "pammfollower",
        "follower_domain": "mailinator.com",
        "follower_count": 0
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
                tok_res = self.session.post(f"{self.base_url}/api/auth/chart-token", timeout=15)
                if tok_res.status_code == 200:
                    data = tok_res.json()
                    self.chart_token = data.get("token")
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

    def update_single_group(self, g: MasterFollowerGroup):
        try:
            # 1. Master Data & Shares
            m_funds = g.master_session.get_funds(self.instance)
            m_pos = g.master_session.get_positions(self.instance)
            m_hist = g.master_session.get_history(self.instance)
            m_shares_res = g.master_session.get_mam_shares(self.instance) if g.id == "mam" else {}

            master_earned_shares = float(m_shares_res.get("master_share_total", 0.0))

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
                "profit_shares_earned": master_earned_shares
            }

            # 2. Fetch Follower Details & Individual Profit Shares
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
                follow_obj = following_list[0] if following_list else {}

                starting_balance = float(follow_obj.get("starting_balance", 10000000.0 if g.id == "mam" else 100000000.0))
                share_pct = float(follow_obj.get("share_percent", 50.0))
                method = follow_obj.get("method", "equity" if g.id == "mam" else "multiplier")
                multiplier = float(follow_obj.get("multiplier", 1.0))
                following_manager = g.master_email

                # Fetch MAM profit shares on follower
                shares_data = s.get_mam_shares(self.instance) if g.id == "mam" else {}
                shared_to_master_total = float(shares_data.get("master_share_total", 0.0))
                shares_history = shares_data.get("shares", [])

                # Follower's profit kept
                total_kept = sum(float(sh.get("follower_share", 0.0)) for sh in shares_history)
                if not total_kept and bal > starting_balance:
                    total_kept = bal - starting_balance

                is_above_hwm = (bal > starting_balance)

                return {
                    "email": email,
                    "name": s.name,
                    "member_id": s.member_id or "N/A",
                    "balance": bal,
                    "equity": eq,
                    "benchmark": starting_balance,
                    "above_benchmark": is_above_hwm,
                    "following": f"{following_manager} ({int(share_pct)}% share)",
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
                            for p in res.get("positions", []):
                                p_copy = p.copy()
                                p_copy["account"] = res["email"]
                                follower_positions.append(p_copy)
                        except Exception:
                            pass

            followers_list.sort(key=lambda x: int(re.search(r"\d+", x["email"]).group(0)) if re.search(r"\d+", x["email"]) else 0)

            # 3. Master Positions Tagged
            master_positions = []
            for p in m_pos:
                p_copy = p.copy()
                p_copy["account"] = g.master_email
                master_positions.append(p_copy)

            # 4. Global Summaries & Totals
            tot_f_bal = sum(f["balance"] for f in followers_list)
            tot_f_eq = sum(f["equity"] for f in followers_list)
            tot_f_pos = sum(f["open_positions_count"] for f in followers_list)
            tot_f_pnl = sum(f["unrealized_pnl"] for f in followers_list)

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
                "active_replication_rate": rep_rate,
                "total_closed_trades": total_closed,
                "win_rate_percent": win_rate,
                "follower_count": len(followers_list)
            }

            g.cache = {
                "master": master_data,
                "followers": followers_list,
                "master_positions": master_positions,
                "follower_positions": follower_positions,
                "history": m_hist,
                "summary": summary
            }

        except Exception:
            pass

    def background_poller(self, interval: int = 3):
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
      max-width: 950px;
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
        <option value="mam">MAM Master (mammaster - 100 Followers)</option>
        <option value="copy">Copy Trading Master (ctmaster - 100 Followers)</option>
        <option value="pamm">PAMM Master (pammmaster)</option>
      </select>
    </div>

    <div class="top-controls">
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
            <th>Symbol</th>
            <th>Side</th>
            <th>Lot Size</th>
            <th>Avg Entry Price</th>
            <th>Mark Price</th>
            <th>Unrealized P&L</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody id="masterPositionsBody">
          <tr><td colspan="10" class="empty-row">No active open positions on Master account. Clean slate.</td></tr>
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
            <th>Symbol</th>
            <th>Side</th>
            <th>Copied Lot Size</th>
            <th>Entry Price</th>
            <th>Current CMP</th>
            <th>Unrealized P&L</th>
            <th>Replication Status</th>
          </tr>
        </thead>
        <tbody id="followerPositionsBody">
          <tr><td colspan="9" class="empty-row">No open replicated follower positions active.</td></tr>
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
            <th>Balance</th>
            <th>Equity</th>
            <th>Benchmark (HWM)</th>
            <th>Above HWM?</th>
            <th>Following (Manager)</th>
            <th>Sizing Method</th>
            <th>Profit Shared to Master</th>
            <th>Profit Kept (Follower)</th>
            <th>Unrealized P&L</th>
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
            <th>Symbol</th>
            <th>Side</th>
            <th>Qty</th>
            <th>Entry Price</th>
            <th>Exit Price</th>
            <th>Realized P&L</th>
            <th>Exit Source</th>
            <th>Attribution</th>
          </tr>
        </thead>
        <tbody id="historyTableBody">
          <tr><td colspan="10" class="empty-row">No trade history recorded yet.</td></tr>
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
                <th>Trade Gross P&L</th>
                <th>Balance Before</th>
                <th>Above Benchmark?</th>
                <th>Manager Share (50%)</th>
                <th>Follower Kept</th>
              </tr>
            </thead>
            <tbody id="modalSharesTableBody">
              <tr><td colspan="7" class="empty-row">No trade shares recorded for this follower yet.</td></tr>
            </tbody>
          </table>
        </div>
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

    function switchTab(tabId, element) {
      activeTab = tabId;
      document.querySelectorAll('.tab-item').forEach(b => b.classList.remove('active'));
      element.classList.add('active');

      document.getElementById('tabContentMasterPos').style.display = tabId === 'master-pos' ? 'block' : 'none';
      document.getElementById('tabContentFollowerPos').style.display = tabId === 'follower-pos' ? 'block' : 'none';
      document.getElementById('tabContentFollowersLedger').style.display = tabId === 'followers-ledger' ? 'block' : 'none';
      document.getElementById('tabContentTradeHistory').style.display = tabId === 'trade-history' ? 'block' : 'none';
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
        btn.innerText = "Auto-Sync: 3s";
        startAutoSync();
      } else {
        btn.classList.remove('active');
        btn.innerText = "Auto-Sync: PAUSED";
        clearInterval(syncInterval);
      }
    }

    function startAutoSync() {
      clearInterval(syncInterval);
      syncInterval = setInterval(fetchDashboardData, 3000);
    }

    function fmtMoney(num) {
      return '$' + Number(num || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    async function fetchDashboardData() {
      try {
        const res = await fetch(`/api/data?master=${activeMasterId}`);
        if (!res.ok) return;
        currentData = await res.json();
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
      document.getElementById('kpiOpenPositions').innerText = masterPos.length + followerPos.length;

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

      // Render Tables
      renderMasterPositions();
      renderFollowerPositions();
      renderFollowersLedger();
      renderHistoryTable();
    }

    // 1. Master Active Positions Table
    function renderMasterPositions() {
      const tbody = document.getElementById('masterPositionsBody');
      const positions = currentData.master_positions || [];

      if (positions.length === 0) {
        tbody.innerHTML = '<tr><td colspan="10" class="empty-row">No active open positions on Master account. Clean slate.</td></tr>';
        return;
      }

      tbody.innerHTML = positions.map(p => {
        const sideClass = (p.side || '').toUpperCase() === 'BUY' ? 'badge-buy' : 'badge-sell';
        const pnl = Number(p.unrealized_pnl || 0);
        const pnlClass = pnl > 0 ? 'text-green' : (pnl < 0 ? 'text-red' : '');

        return `<tr>
          <td><span class="badge badge-master">MASTER</span></td>
          <td style="font-weight: 700;">${p.account}</td>
          <td style="font-size: 11px; color: var(--text-muted);">${p.market_order_id || p.order_id || 'N/A'}</td>
          <td><strong>${p.symbol}</strong></td>
          <td><span class="badge ${sideClass}">${p.side}</span></td>
          <td>${Number(p.net_qty || p.qty || 0).toFixed(2)}</td>
          <td>${Number(p.avg_entry_price || p.fill_price || 0).toFixed(2)}</td>
          <td>${Number(p.current_price || p.avg_entry_price || 0).toFixed(2)}</td>
          <td class="${pnlClass}">${fmtMoney(pnl)}</td>
          <td><span class="badge badge-buy">ACTIVE</span></td>
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
        tbody.innerHTML = '<tr><td colspan="9" class="empty-row">No open replicated follower positions active.</td></tr>';
        return;
      }

      tbody.innerHTML = filtered.map(p => {
        const sideClass = (p.side || '').toUpperCase() === 'BUY' ? 'badge-buy' : 'badge-sell';
        const pnl = Number(p.unrealized_pnl || 0);
        const pnlClass = pnl > 0 ? 'text-green' : (pnl < 0 ? 'text-red' : '');

        return `<tr>
          <td style="font-weight: 700;">${p.account}</td>
          <td style="font-size: 11px; color: var(--text-muted);">${p.market_order_id || 'N/A'}</td>
          <td><strong>${p.symbol}</strong></td>
          <td><span class="badge ${sideClass}">${p.side}</span></td>
          <td>${Number(p.net_qty || p.qty || 0).toFixed(2)}</td>
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

        return `<tr class="clickable-row" onclick="openFollowerModal('${f.email}')" title="Click to view full order history & profit share breakdown">
          <td style="color: var(--text-dim);">${i + 1}</td>
          <td style="font-weight: 700; color: #60a5fa;">
            ${f.email} <span style="font-size: 11px; color: var(--text-dim); margin-left: 4px;">🔍</span>
          </td>
          <td>${fmtMoney(f.balance)}</td>
          <td>${fmtMoney(f.equity)}</td>
          <td style="font-weight: 600;">${fmtMoney(f.benchmark)}</td>
          <td>${aboveBadge}</td>
          <td style="font-size: 12px; color: #cbd5e1;">${f.following || 'mammaster (50%)'}</td>
          <td style="text-transform: capitalize;">${f.method} (${f.multiplier}x)</td>
          <td><span class="badge badge-shared">+${fmtMoney(f.shared_to_master)}</span></td>
          <td class="text-green" style="font-weight: 700;">+${fmtMoney(f.profit_kept)}</td>
          <td class="${pnlClass}">${fmtMoney(pnl)}</td>
          <td>
            <button class="btn" style="padding: 4px 10px; font-size: 11px;" onclick="event.stopPropagation(); openFollowerModal('${f.email}')">View History</button>
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
        tbody.innerHTML = '<tr><td colspan="10" class="empty-row">No closed trade records found.</td></tr>';
        return;
      }

      tbody.innerHTML = list.map(h => {
        const sideClass = (h.side || '').toUpperCase() === 'BUY' ? 'badge-buy' : 'badge-sell';
        const pnl = Number(h.realized_pnl || 0);
        const pnlClass = pnl > 0 ? 'text-green' : (pnl < 0 ? 'text-red' : '');
        const timeStr = h.executed_at ? h.executed_at.replace('T', ' ').slice(0, 19) : 'N/A';

        return `<tr>
          <td style="color: var(--text-dim); font-size: 11px;">#${h.history_id || 'N/A'}</td>
          <td style="font-size: 11px; color: var(--text-muted);">${timeStr}</td>
          <td><strong>${h.symbol}</strong></td>
          <td><span class="badge ${sideClass}">${h.side}</span></td>
          <td>${Number(h.qty || 0).toFixed(2)}</td>
          <td>${Number(h.entry_price || 0).toFixed(2)}</td>
          <td>${Number(h.exit_price || 0).toFixed(2)}</td>
          <td class="${pnlClass}" style="font-weight: 700;">${fmtMoney(pnl)}</td>
          <td style="font-size: 11px; text-transform: uppercase;">${h.exit_source || h.exit_type || 'N/A'}</td>
          <td style="font-size: 11px; color: var(--text-muted);">${h.entry_copy_kind || h.attribution || 'master'}</td>
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
        tbody.innerHTML = '<tr><td colspan="7" class="empty-row">No trade profit shares recorded for this follower yet.</td></tr>';
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

          return `<tr>
            <td>#${s.trade_id || s.share_id || 'N/A'}</td>
            <td style="font-size: 11px; color: var(--text-muted);">${timeStr}</td>
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

    function closeModalOnBackdrop(e) {
      if (e.target.id === 'followerModal') {
        closeFollowerModal();
      }
    }

    // Initialize
    fetchDashboardData();
    startAutoSync();
  </script>
</body>
</html>
"""


class DashboardHTTPRequestHandler(BaseHTTPRequestHandler):
    data_manager: MultiMasterDashboardManager = None

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        url_parts = self.path.split("?")
        path = url_parts[0]
        query = url_parts[1] if len(url_parts) > 1 else ""

        if path in ["/", "/index.html"]:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(ENTERPRISE_DASHBOARD_HTML.encode("utf-8"))

        elif path == "/api/data":
            master_param = "mam"
            if "master=" in query:
                for q in query.split("&"):
                    if q.startswith("master="):
                        master_param = q.split("=")[1].strip()

            target_group = self.data_manager.groups.get(master_param, self.data_manager.groups["mam"])

            with self.data_manager.lock:
                cache_copy = target_group.cache.copy()
                cache_copy["meta"] = {
                    "last_updated": self.data_manager.last_update_str,
                    "active_master": master_param,
                    "status": "LIVE"
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
    print(f"[*] Masters Supported   : MAM (mammaster), Copy Trading (ctmaster), PAMM (pammmaster)")
    print("=" * 85 + "\n")

    manager = MultiMasterDashboardManager(base_url=url, password=password)

    # Start background poller thread
    t = threading.Thread(target=manager.background_poller, kwargs={"interval": 3}, daemon=True)
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
