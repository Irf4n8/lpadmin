"""
Centralized Configuration Loader
================================
Loads all configuration and secrets from the root .env file.
Provides safe fallbacks if .env or python-dotenv is missing.
"""

import os
from pathlib import Path

# Project root directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=BASE_DIR / ".env")
except ImportError:
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        import re
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    m = re.match(r"^([A-Za-z0-9_]+)\s*[-=:]\s*(.+)$", line)
                    if m:
                        k, v = m.group(1).strip(), m.group(2).strip().strip("'\"")
                        os.environ.setdefault(k, v)

# Environment settings
BASE_URL = os.getenv("URL", os.getenv("BASE_URL", "https://lpadmin.blackfx.com")).rstrip("/")
if "/blackadmin" in BASE_URL:
    BASE_URL = BASE_URL.replace("/blackadmin", "")

ADMIN_EMAIL = os.getenv("ADMIN_ID", os.getenv("ADMIN_EMAIL", "lpadmin@blacktrader.com"))
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
MEMBER_PASSWORD = os.getenv("FOLLOWERS_PASSWORD", os.getenv("MEMBER_PASSWORD", "Test@1234"))
MAM_MASTER = os.getenv("MAM_MASTER", "mammaster@mailinator.com")
DEFAULT_BALANCE = float(os.getenv("DEFAULT_BALANCE", "100000000"))
DEFAULT_PREFIX = os.getenv("DEFAULT_EMAIL_PREFIX", "mamfollower")
DEFAULT_DOMAIN = os.getenv("DEFAULT_EMAIL_DOMAIN", "mailinator.com")
DEFAULT_INSTANCES = os.getenv("DEFAULT_INSTANCES", "paper,real")


# --- Dashboard / copy-trading topology (additive; defaults match the previously hardcoded dashboard values) ---
MASTER_EMAIL = os.getenv("MASTER_EMAIL", "ctmaster@mailinator.com")
MASTER_ID = os.getenv("MASTER_ID", "mem_aac4ca423a6925dca7")
FOLLOWER_COUNT = int(os.getenv("FOLLOWER_COUNT", "100"))
FOLLOWER_PREFIX = os.getenv("FOLLOWER_PREFIX", "follower")

# Dashboard server. Token is optional: when set, every request must carry it (open /?token=<DASHBOARD_TOKEN> once).
DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "0.0.0.0")
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT") or os.getenv("PORT") or "5000")
DASHBOARD_TOKEN = os.getenv("DASHBOARD_TOKEN", "")
