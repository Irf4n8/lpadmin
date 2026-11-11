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

