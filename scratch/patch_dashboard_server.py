import re

with open('dashboard_server.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update MASTERS_CONFIG
old_config = '''MASTERS_CONFIG = {
    "mam": {
        "id": "mam",
        "name": "MAM Master (Multi-Account Manager)",
        "email": "mamm@mailinator.com",
        "client_id": "mem_e2dbce29e1c71a7bf6",
        "type": "MAM",
        "follower_prefix": "mamfollower",
        "follower_domain": "mailinator.com",
        "follower_count": 100
    }
}'''

new_config = '''MASTERS_CONFIG = {
    "mam": {
        "id": "mam",
        "name": "MAM Master (Multi-Account Manager)",
        "email": "mamm@mailinator.com",
        "client_id": "mem_11434b0b9d9d210899",
        "type": "MAM",
        "follower_prefix": "mamf",
        "follower_domain": "mailinator.com",
        "follower_count": 100
    }
}'''

assert old_config in content, "old_config not found!"
content = content.replace(old_config, new_config)

# 2. Update MasterFollowerGroup to store follower_prefix and dynamically update master_client_id
old_mfg = '''        self.master_session = TraderSession(self.master_email, self.password, f"Master-{self.id}", self.base_url, role="master")
        self.follower_sessions: Dict[str, TraderSession] = {}
        if self.follower_count > 0:
            for i in range(1, self.follower_count + 1):
                email = f"{cfg['follower_prefix']}{i}@{cfg['follower_domain']}"
                self.follower_sessions[email] = TraderSession(email, self.password, f"f{i}", self.base_url, role="follower")'''

new_mfg = '''        self.master_session = TraderSession(self.master_email, self.password, f"Master-{self.id}", self.base_url, role="master")
        self.follower_sessions: Dict[str, TraderSession] = {}
        self.follower_prefix = cfg.get("follower_prefix", "mamf")
        self.follower_domain = cfg.get("follower_domain", "mailinator.com")
        if self.follower_count > 0:
            for i in range(1, self.follower_count + 1):
                email = f"{self.follower_prefix}{i}@{self.follower_domain}"
                self.follower_sessions[email] = TraderSession(email, self.password, f"f{i}", self.base_url, role="follower")'''

assert old_mfg in content, "old_mfg not found!"
content = content.replace(old_mfg, new_mfg)

# 3. Update MultiMasterDashboardManager.__init__ instance to "real"
old_mm_init = '''class MultiMasterDashboardManager:
    def __init__(self, base_url: str, password: str):
        self.base_url = base_url
        self.password = password
        self.instance = "paper"'''

new_mm_init = '''class MultiMasterDashboardManager:
    def __init__(self, base_url: str, password: str):
        self.base_url = base_url
        self.password = password
        env = load_env_file(".env")
        self.instance = env.get("INSTANCE", env.get("DEFAULT_INSTANCE", "real"))'''

assert old_mm_init in content, "old_mm_init not found!"
content = content.replace(old_mm_init, new_mm_init)

# 4. In handlers: ensure master_client_id uses master_session.member_id or master_client_id, and range uses g.follower_prefix
# Line 686: master_client_id = g.master_client_id
# Line 694: em = f"mamfollower{i}@mailinator.com"
old_unfollow_block = '''        master_client_id = g.master_client_id

        target_sessions = []
        if target_type == "single":
            if single_email in g.follower_sessions:
                target_sessions.append(g.follower_sessions[single_email])
        elif target_type == "range":
            for i in range(start, end + 1):
                em = f"mamfollower{i}@mailinator.com"
                if em in g.follower_sessions:
                    target_sessions.append(g.follower_sessions[em])'''

new_unfollow_block = '''        master_client_id = g.master_session.member_id or g.master_client_id

        target_sessions = []
        if target_type == "single":
            if single_email in g.follower_sessions:
                target_sessions.append(g.follower_sessions[single_email])
        elif target_type == "range":
            for i in range(start, end + 1):
                em = f"{getattr(g, 'follower_prefix', 'mamf')}{i}@{getattr(g, 'follower_domain', 'mailinator.com')}"
                if em in g.follower_sessions:
                    target_sessions.append(g.follower_sessions[em])'''

assert old_unfollow_block in content, "old_unfollow_block not found!"
content = content.replace(old_unfollow_block, new_unfollow_block)

# Category change block
old_cat_block = '''        master_client_id = g.master_client_id

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
                    target_sessions.append(g.follower_sessions[em])'''

new_cat_block = '''        master_client_id = g.master_session.member_id or g.master_client_id

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
                em = f"{getattr(g, 'follower_prefix', 'mamf')}{i}@{getattr(g, 'follower_domain', 'mailinator.com')}"
                if em in g.follower_sessions:
                    target_sessions.append(g.follower_sessions[em])'''

assert old_cat_block in content, "old_cat_block not found!"
content = content.replace(old_cat_block, new_cat_block)

# Book change block
old_book_block = '''        target_sessions = []
        if target_type == "single":
            if single_email in g.follower_sessions:
                target_sessions.append(g.follower_sessions[single_email])
        elif target_type == "range":
            for i in range(start, end + 1):
                em = f"mamfollower{i}@mailinator.com"
                if em in g.follower_sessions:
                    target_sessions.append(g.follower_sessions[em])'''

new_book_block = '''        target_sessions = []
        if target_type == "single":
            if single_email in g.follower_sessions:
                target_sessions.append(g.follower_sessions[single_email])
        elif target_type == "range":
            for i in range(start, end + 1):
                em = f"{getattr(g, 'follower_prefix', 'mamf')}{i}@{getattr(g, 'follower_domain', 'mailinator.com')}"
                if em in g.follower_sessions:
                    target_sessions.append(g.follower_sessions[em])'''

# There are multiple occurrences of this target_sessions pattern:
# in handle_book_change, handle_broker_setting_change, handle_balance_change!
count = content.count(old_book_block)
print(f"Replacing {count} occurrences of target_sessions range block...")
content = content.replace(old_book_block, new_book_block)

# In handle_broker_setting_change: master_client_id = g.master_client_id
content = content.replace(
    '        master_client_id = g.master_client_id\n        target_inst = target_broker.lower()',
    '        master_client_id = g.master_session.member_id or g.master_client_id\n        target_inst = target_broker.lower()'
)

# 5. UI replacements
content = content.replace('mem_e2dbce29e1c71a7bf6', 'mem_11434b0b9d9d210899')
content = content.replace('placeholder="Filter positions by follower (e.g. mamfollower12)..."', 'placeholder="Filter positions by follower (e.g. mamf12)..."')
content = content.replace('placeholder="Search accounts (e.g. mamfollower45)..."', 'placeholder="Search accounts (e.g. mamf45)..."')
content = content.replace('<h2 id="modalFollowerEmail">mamfollower1@mailinator.com</h2>', '<h2 id="modalFollowerEmail">mamf1@mailinator.com</h2>')
content = content.replace('<div id="modalMgrName">mammaster (50%)</div>', '<div id="modalMgrName">mamm (50%)</div>')
content = content.replace('value="mammaster"', 'value="mamm"')
content = content.replace('(mamfollower1 .. mamfollower100)', '(mamf1 .. mamf100)')
content = content.replace('<h2 id="quickManageEmail">mamfollower1@mailinator.com</h2>', '<h2 id="quickManageEmail">mamf1@mailinator.com</h2>')
content = content.replace("master.mam_display_name || 'mammaster'", "master.mam_display_name || 'mamm'")
content = content.replace("f.following || 'mammaster (50%)'", "f.following || 'mamm (50%)'")
content = content.replace("document.getElementById('masterDisplayNameInput').value.trim() || 'mammaster'", "document.getElementById('masterDisplayNameInput').value.trim() || 'mamm'")
content = content.replace("Master ID=mammaster", "Master ID=mamm")
content = content.replace("mammaster (50%)", "mamm (50%)")

with open('dashboard_server.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Successfully patched dashboard_server.py!")
