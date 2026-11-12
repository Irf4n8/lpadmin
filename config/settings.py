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
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

# Environment settings
BASE_URL = os.getenv("BASE_URL", "https://lpadmin.blackfx.com").rstrip("/")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
MEMBER_PASSWORD = os.getenv("MEMBER_PASSWORD", "")
DEFAULT_BALANCE = float(os.getenv("DEFAULT_BALANCE", "100000000"))
DEFAULT_PREFIX = os.getenv("DEFAULT_EMAIL_PREFIX", "follower")
DEFAULT_DOMAIN = os.getenv("DEFAULT_EMAIL_DOMAIN", "mailinator.com")
DEFAULT_INSTANCES = os.getenv("DEFAULT_INSTANCES", "paper,real")


# --- Copy-trading topology (override in .env for your own master / follower set) ---
MASTER_EMAIL = os.getenv("MASTER_EMAIL", "ctmaster@mailinator.com")
MASTER_ID = os.getenv("MASTER_ID", "mem_aac4ca423a6925dca7")
FOLLOWER_COUNT = int(os.getenv("FOLLOWER_COUNT", "100"))

# --- Dashboard server ---
# Binds to localhost by default. Set DASHBOARD_HOST=0.0.0.0 only together with DASHBOARD_TOKEN.
DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "127.0.0.1")
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT") or os.getenv("PORT") or "5000")
DASHBOARD_TOKEN = os.getenv("DASHBOARD_TOKEN", "")
