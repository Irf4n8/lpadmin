# BlackTrader Automation Suite

A modular automation toolkit for **BlackTrader / BlackFX** (`https://lpadmin.blackfx.com`) featuring:
* Bulk trader account creation & funding (Paper and Real accounts).
* Copy-trading automation (listing masters, following with custom lot sizing/multipliers).
* Dual implementation: **Playwright Browser Automation** and **Direct HTTP API**.
* Clean architecture, centralized configuration, and Git-safe secrets management.

---

## 📁 Repository Structure

```
lpadmin/
├── .env                              # Local active credentials & defaults (gitignored)
├── .env.example                      # Safe credential-free template for GitHub
├── .gitignore                        # Git exclusion rules
├── requirements.txt                  # Python dependencies
├── README.md                         # Project documentation
├── main.py                           # Unified CLI runner
├── conversation_history.txt          # Complete conversation history & AI agent briefing
│
├── config/                           # Centralized configuration
│   ├── __init__.py
│   └── settings.py                   # Environment loader with safe fallbacks
│
├── scripts/                          # Automation scripts
│   ├── __init__.py
│   ├── playwright_create_accounts.py # Browser-based bulk account creator & funder
│   ├── playwright_follow_master.py   # Browser-based copy trading follower
│   ├── api_create_accounts.py        # Direct HTTP API account creator
│   └── api_follow_master.py          # Direct HTTP API copy trading follower
│
└── docs/                             # Documentation & architecture guides
    ├── API_DOCUMENTATION.md          # Endpoints, schemas, payloads, and auth flows
    └── conversation_history.txt      # Full session logs & AI handoff notes
```

---

## 🚀 Quickstart

### 1. Installation
```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure Environment (`.env`)
```bash
cp .env.example .env
```
Fill in your credentials in `.env`:
```env
BASE_URL=https://lpadmin.blackfx.com
ADMIN_EMAIL=lpadmin@blacktrader.com
ADMIN_PASSWORD=Raj1234!
MEMBER_PASSWORD=Test@1234
DEFAULT_BALANCE=100000000
DEFAULT_EMAIL_PREFIX=follower
DEFAULT_EMAIL_DOMAIN=mailinator.com
DEFAULT_INSTANCES=paper,real
```

---

## 💻 CLI Commands (`main.py`)

### 1. List Available Copy Masters
```bash
python main.py list-masters
```

### 2. Bulk Create Accounts & Fund Balances (10 Crore)
```bash
# Headless (follower1 to follower100)
python main.py create --start 1 --end 100

# With visible browser window (headed mode)
python main.py create --headed --start 1 --end 10

# Custom range and balance (e.g., 5 Crore = 50,000,000)
python main.py create --start 101 --end 150 --balance 50000000
```

### 3. Make Accounts Follow a Master Trader
```bash
# Make follower1 to follower100 copy master "ctmaster"
python main.py follow --master "ctmaster" --start 1 --end 100

# Copy on both Paper and Real accounts with a 2.0x multiplier
python main.py follow --master "ctmaster" --instance both --multiplier 2.0 --start 1 --end 100

# Trade opposite side (Buy becomes Sell)
python main.py follow --master "ctmaster" --reverse --start 1 --end 50
```

---

## ⚡ Direct Script Access
You can also run any script directly from the `scripts/` directory:
```bash
python scripts/playwright_create_accounts.py --start 1 --end 100
python scripts/playwright_follow_master.py --master "ctmaster" --start 1 --end 100
python scripts/api_create_accounts.py --start 1 --end 100
python scripts/api_follow_master.py --master "ctmaster" --start 1 --end 100
```
*(For backwards compatibility, root-level scripts are also maintained).*
