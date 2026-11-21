"""Rebuild the full Terminal Postman collection for the current OMS API contract."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = [
    ROOT / "postman" / "BlackTrader Terminal Full API Collection.postman_collection.json",
    ROOT / "terminal_api_collection" / "BlackTrader Terminal Full API Collection.postman_collection.json",
]
BASE = "{{base_url}}/test"
OMS = BASE + "/v1/oms"
REAL = OMS + "/real"
ADMIN = BASE + "/admin/api"


def event(listen: str, lines: list[str]) -> dict:
    return {"listen": listen, "script": {"type": "text/javascript", "exec": lines}}


def item(
    name: str,
    method: str,
    url: str,
    *,
    token: str | None = None,
    body: dict | str | None = None,
    tests: list[str] | None = None,
    prerequest: list[str] | None = None,
    description: str = "",
    broker_header: bool = True,
) -> dict:
    headers: list[dict[str, str]] = []
    if body is not None:
        headers.append({"key": "Content-Type", "value": "application/json"})
    if token:
        headers.append({"key": "Authorization", "value": f"Bearer {{{{{token}}}}}"})
    if token and broker_header and "/v1/oms/" in url:
        headers.append({"key": "X-Broker-ID", "value": "real"})
    request: dict = {
        "method": method,
        "header": headers,
        "url": url,
        "description": description,
    }
    if body is not None:
        raw = body if isinstance(body, str) else json.dumps(body, indent=2)
        request["body"] = {"mode": "raw", "raw": raw, "options": {"raw": {"language": "json"}}}
    result = {"name": name, "request": request}
    events = []
    if prerequest:
        events.append(event("prerequest", prerequest))
    if tests:
        events.append(event("test", tests))
    if events:
        result["event"] = events
    return result


def folder(name: str, description: str, children: list[dict]) -> dict:
    return {"name": name, "description": description, "item": children}


def login(name: str, email_var: str, password_var: str, token_var: str, client_var: str) -> dict:
    return item(
        name,
        "POST",
        OMS + "/_auth/login",
        body={"email": f"{{{{{email_var}}}}}", "password": f"{{{{{password_var}}}}}"},
        broker_header=False,
        description="Current terminal authentication endpoint. The returned OMS bearer token is used directly; no chart-token exchange is required.",
        tests=[
            "let j = {}; try { j = pm.response.json(); } catch (e) {}",
            f"pm.test('{name}: HTTP 200', () => pm.response.to.have.status(200));",
            "pm.test('Login succeeded and returned a token', () => { pm.expect(j.success).to.eql(true); pm.expect(j.token).to.be.a('string').and.not.empty; });",
            f"if (j.token) {{ pm.environment.set('{token_var}', j.token); }}",
            f"if (j.token) {{ pm.environment.set('{token_var.replace('_oms_', '_')}', j.token); }}",
            "const memberId = j.member && (j.member.member_id || j.member.client_id || j.member.id);",
            f"if (memberId) {{ pm.environment.set('{client_var}', memberId); }}",
        ],
    )


def info(name: str, token_var: str) -> dict:
    return item(
        name,
        "GET",
        REAL + "/info",
        token=token_var,
        description="Confirms that the authenticated token is bound to the Real Hedging engine.",
        tests=[
            "const j = pm.response.json();",
            "pm.test('Instance info returned', () => pm.response.to.have.status(200));",
            "pm.test('Real Hedging confirmed', () => { pm.expect(j.slug).to.eql('real'); pm.expect(j.mode).to.eql('hedging'); });",
        ],
    )


def standard_success(label: str) -> list[str]:
    return [
        "let j = {}; try { j = pm.response.json(); } catch (e) {}",
        f"pm.test('{label}: HTTP 200', () => pm.response.to.have.status(200));",
        "pm.test('Operation did not report failure', () => pm.expect(j.success).to.not.eql(false));",
    ]


def position_reader(name: str, token_var: str, one_id_var: str | None = None) -> dict:
    tests = [
        "const j = pm.response.json();",
        "pm.test('Positions and funds returned', () => { pm.response.to.have.status(200); pm.expect(j.positions).to.be.an('array'); pm.expect(j.funds).to.be.an('object'); });",
    ]
    if one_id_var:
        tests += [
            "if (j.positions.length) {",
            "  const id = j.positions[0].market_order_id || j.positions[0].position_id || j.positions[0].id;",
            f"  if (id) pm.environment.set('{one_id_var}', id);",
            "}",
        ]
    return item(name, "GET", REAL + "/positions", token=token_var, tests=tests)


def unique_order_ids() -> list[str]:
    return [
        "const suffix = Date.now() + '_' + Math.random().toString(16).slice(2);",
        "pm.collectionVariables.set('request_id', 'postman_req_' + suffix);",
        "pm.collectionVariables.set('group_id', 'postman_grp_' + suffix);",
    ]


def order_tests(label: str) -> list[str]:
    return [
        "const j = pm.response.json();",
        f"pm.test('{label}: HTTP 200', () => pm.response.to.have.status(200));",
        "pm.test('Order accepted', () => pm.expect(j.success).to.eql(true));",
        "const p = j.position || {}; const o = j.order || {};",
        "const id = p.market_order_id || o.market_order_id || o.order_id || j.order_id;",
        "if (id) pm.environment.set('master_position_id', id);",
    ]


def pending_tests(label: str) -> list[str]:
    return [
        "const j = pm.response.json();",
        f"pm.test('{label}: HTTP 200', () => pm.response.to.have.status(200));",
        "pm.test('Pending order accepted', () => pm.expect(j.success).to.eql(true));",
        "const o = j.order || {}; const id = o.order_id || j.order_id;",
        "if (id) pm.environment.set('pending_order_id', id);",
    ]


def follow(name: str, token: str, method: str, multiplier: float, master_var: str = "master_client_id") -> dict:
    return item(
        name,
        "POST",
        REAL + "/mam/follow",
        token=token,
        body={"master_client_id": f"{{{{{master_var}}}}}", "method": method, "multiplier": multiplier},
        tests=standard_success(name),
        description="Creates, reactivates, or updates the follower's MAM relationship using the current mam/follow contract.",
    )


auth = folder(
    "0. Auth Setup",
    "Run this folder first. Trader login now returns the OMS bearer token directly; no separate browser-session or chart-token exchange is required.",
    [
        item(
            "Admin Login (optional)", "POST", ADMIN + "/login",
            body={"email": "{{admin_email}}", "password": "{{admin_password}}", "remember": True},
            broker_header=False,
            description="Optional client-admin login. Requires separate admin credentials; trader credentials cannot access this API.",
            tests=[
                "let j = {}; try { j = pm.response.json(); } catch (e) {}",
                "pm.test('Admin login returned 200', () => pm.response.to.have.status(200));",
                "if (j.token) pm.environment.set('admin_token', j.token);",
                "pm.test('Admin token returned', () => pm.expect(j.token).to.be.a('string').and.not.empty);",
            ],
        ),
        login("Master Trader Login", "master_email", "master_password", "master_oms_token", "master_client_id"),
        info("Master — Confirm Real Hedging", "master_oms_token"),
        login("Follower 1 Login", "follower1_email", "follower_password", "follower1_oms_token", "follower1_client_id"),
        info("Follower 1 — Confirm Real Hedging", "follower1_oms_token"),
        login("Follower 2 Login", "follower2_email", "follower_password", "follower2_oms_token", "follower2_client_id"),
        info("Follower 2 — Confirm Real Hedging", "follower2_oms_token"),
    ],
)


def set_balance(name: str, member_var: str, amount: int, remark: str) -> dict:
    return item(
        name, "POST", ADMIN + f"/members/{{{{{member_var}}}}}/balance", token="admin_token",
        body={"instance": "real", "balance": amount, "force": True, "remark": remark},
        broker_header=False,
        description="Admin-only Real Hedging balance change. Do not run while the member has open positions unless that race is the intended test.",
        tests=[
            "let j = {}; try { j = pm.response.json(); } catch (e) {}",
            "pm.test('Admin balance request returned 200', () => pm.response.to.have.status(200));",
            "pm.test('Balance update did not report failure', () => pm.expect(j.success).to.not.eql(false));",
        ],
    )


admin = folder(
    "1. Admin — Member Management (optional)",
    "These routes require an admin token. They are separate from trader authentication.",
    [
        item("List Members", "GET", ADMIN + "/members?limit=50&offset=0", token="admin_token", broker_header=False),
        item("Search Member by Email", "GET", ADMIN + "/members?email={{master_email}}", token="admin_token", broker_header=False),
        set_balance("Set Selected Member Balance", "target_member_id", 10000, "Postman QA balance setup"),
        set_balance("Set Master Balance to 10,000", "master_client_id", 10000, "Postman QA master setup"),
        set_balance("Set Follower 1 Balance to 5,000", "follower1_client_id", 5000, "Postman QA follower setup"),
        set_balance("Set Follower 2 Balance to 5,000", "follower2_client_id", 5000, "Postman QA follower setup"),
    ],
)


account = folder(
    "2. Account, Funds and History",
    "Read-only account state for the three scoped Real Hedging users.",
    [
        position_reader("Master — Positions and Funds", "master_oms_token", "master_position_id"),
        position_reader("Follower 1 — Positions and Funds", "follower1_oms_token", "follower1_position_id"),
        position_reader("Follower 2 — Positions and Funds", "follower2_oms_token", "follower2_position_id"),
        item("Master — Account Terms", "GET", REAL + "/account", token="master_oms_token", tests=standard_success("Account terms")),
        item("Master — Orders", "GET", REAL + "/orders", token="master_oms_token", tests=standard_success("Orders")),
        item("Master — Trading History", "GET", REAL + "/history?limit=50&offset=0", token="master_oms_token", tests=standard_success("History")),
    ],
)


mam = folder(
    "3. MAM — Relationships, Allocation and Fees",
    "Current Real MAM routes. Balance and equity are method names; follower requests do not set the manager's share percentage.",
    [
        item("Master — View Relationships", "GET", REAL + "/mam/follows", token="master_oms_token", tests=standard_success("Master relationships")),
        item("Master — View Profit Shares", "GET", REAL + "/mam/shares", token="master_oms_token", tests=standard_success("Profit shares")),
        item(
            "Master — Update Display Name and Performance Share", "POST", REAL + "/mam/master", token="master_oms_token",
            body='{"display_name": "{{manager_display_name}}", "share_percent": {{manager_share_percent}}}',
            tests=standard_success("Manager configuration"),
        ),
        follow("Follower 1 — Multiplier Allocation", "follower1_oms_token", "multiplier", 1),
        follow("Follower 1 — Balance Allocation", "follower1_oms_token", "balance", 1),
        follow("Follower 1 — Equity Allocation", "follower1_oms_token", "equity", 1),
        follow("Follower 1 — Restore 1x Multiplier", "follower1_oms_token", "multiplier", 1),
        follow("Follower 2 — Set 2x Multiplier", "follower2_oms_token", "multiplier", 2),
        follow("Follower 2 — Restore 1x Multiplier", "follower2_oms_token", "multiplier", 1),
        item("Follower 1 — View Current Relationship", "GET", REAL + "/mam/follows", token="follower1_oms_token", tests=standard_success("Follower relationship")),
        item(
            "Follower 1 — Unfollow Master", "POST", REAL + "/mam/unfollow", token="follower1_oms_token",
            body={"master_client_id": "{{master_client_id}}"}, tests=standard_success("Unfollow"),
            description="Ends the active relationship. The next request restores it so a full folder run finishes in a usable state.",
        ),
        follow("Follower 1 — Rejoin and Restore 1x Multiplier", "follower1_oms_token", "multiplier", 1),
    ],
)


market_body = {
    "symbol": "{{symbol}}", "side": "BUY", "qty": 0.01, "type": "MARKET",
    "request_id": "{{request_id}}", "group_id": "{{group_id}}", "source": "postman", "tag": "TERMINAL_API_QA",
}

orders = folder(
    "4. Orders — Market and Pending",
    "These requests place real-engine test orders and may copy them to active MAM followers. Use dedicated test accounts and run teardown afterward.",
    [
        item("Place Market BUY", "POST", REAL + "/orders", token="master_oms_token", body=market_body, prerequest=unique_order_ids(), tests=order_tests("Market BUY")),
        item("Place Market SELL", "POST", REAL + "/orders", token="master_oms_token", body={**market_body, "side": "SELL"}, prerequest=unique_order_ids(), tests=order_tests("Market SELL")),
        item(
            "Place Market BUY with SL and TP", "POST", REAL + "/orders", token="master_oms_token",
            body='{"symbol":"{{symbol}}","side":"BUY","qty":0.01,"type":"MARKET","request_id":"{{request_id}}","group_id":"{{group_id}}","source":"postman","tag":"TERMINAL_API_QA","sl":{{sl_price}},"tp":{{tp_price}}}',
            prerequest=unique_order_ids(), tests=order_tests("Market BUY with protection"),
            description="Current protection fields are sl and tp. Set valid BLACK:BTCUSD levels in the environment before sending.",
        ),
        item(
            "Place Pending BUY LIMIT", "POST", REAL + "/orders/pending", token="master_oms_token",
            body={**market_body, "type": "LIMIT", "price": "{{limit_price}}"}, prerequest=unique_order_ids(), tests=pending_tests("Pending LIMIT"),
        ),
        item(
            "Place Pending BUY STOP", "POST", REAL + "/orders/pending", token="master_oms_token",
            body={**market_body, "type": "STOP", "trigger_price": "{{stop_price}}"}, prerequest=unique_order_ids(), tests=pending_tests("Pending STOP"),
        ),
        item("Modify Saved Pending Order", "PUT", REAL + "/orders/{{pending_order_id}}/modify", token="master_oms_token", body={"price": "{{new_limit_price}}"}, tests=standard_success("Modify pending order")),
        item("Cancel Saved Pending Order", "DELETE", REAL + "/orders/{{pending_order_id}}", token="master_oms_token", tests=standard_success("Cancel pending order")),
        item("Get Trading History", "GET", REAL + "/history?limit=50&offset=0", token="master_oms_token", tests=standard_success("Trading history")),
    ],
)


positions = folder(
    "5. Positions — Reduce, Protection and Close",
    "Uses market_order_id from the current positions response. Partial close is /reduce; protection uses sl, tp and trailing.",
    [
        position_reader("Refresh Master Position ID", "master_oms_token", "master_position_id"),
        item("Reduce Saved Position", "POST", REAL + "/positions/{{master_position_id}}/reduce", token="master_oms_token", body={"qty": 0.005}, tests=standard_success("Reduce position")),
        item("Set or Update SL and TP", "PUT", REAL + "/positions/{{master_position_id}}/protection", token="master_oms_token", body='{"sl":{{sl_price}},"tp":{{tp_price}}}', tests=standard_success("Set protection")),
        item("Set Server Trailing Stop", "PUT", REAL + "/positions/{{master_position_id}}/protection", token="master_oms_token", body={"trailing": {"activation": 200, "distance": 100, "step": 20}}, tests=standard_success("Set trailing stop")),
        item("Remove SL and TP", "PUT", REAL + "/positions/{{master_position_id}}/protection", token="master_oms_token", body={"sl": 0, "tp": 0}, tests=standard_success("Remove protection")),
        item("Square Off Saved Position", "POST", REAL + "/positions/{{master_position_id}}/squareoff", token="master_oms_token", body={}, tests=standard_success("Square off")),
    ],
)


def cleanup_read(name: str, token: str, prefix: str) -> list[dict]:
    return [
        item(
            f"{name} — Read Open Positions for Cleanup", "GET", REAL + "/positions", token=token,
            tests=[
                "const j = pm.response.json(); pm.test('Positions read', () => pm.response.to.have.status(200));",
                "const ids = (j.positions || []).map(p => p.market_order_id || p.position_id || p.id).filter(Boolean);",
                f"pm.collectionVariables.set('{prefix}_position_ids_json', JSON.stringify(ids));",
            ],
        ),
        item(
            f"{name} — Bulk Square Off Open Positions", "POST", REAL + "/positions/bulk/squareoff", token=token,
            body='{"market_order_ids": {{' + prefix + '_position_ids_json}}, "source": "postman_cleanup"}',
            prerequest=[
                f"const ids = JSON.parse(pm.collectionVariables.get('{prefix}_position_ids_json') || '[]');",
                "if (!ids.length) { pm.execution.skipRequest(); }",
            ],
            tests=standard_success("Bulk squareoff"),
        ),
        item(
            f"{name} — Read Working Orders for Cleanup", "GET", REAL + "/orders", token=token,
            tests=[
                "const j = pm.response.json(); pm.test('Orders read', () => pm.response.to.have.status(200));",
                "const working = new Set(['PENDING', 'OPEN', 'NEW']);",
                "const ids = (j.orders || []).filter(o => working.has(o.state)).map(o => o.order_id).filter(Boolean);",
                f"pm.collectionVariables.set('{prefix}_pending_ids_json', JSON.stringify(ids));",
            ],
        ),
        item(
            f"{name} — Bulk Cancel Working Orders", "POST", REAL + "/orders/bulk/cancel", token=token,
            body='{"order_ids": {{' + prefix + '_pending_ids_json}}, "source": "postman_cleanup"}',
            prerequest=[
                f"const ids = JSON.parse(pm.collectionVariables.get('{prefix}_pending_ids_json') || '[]');",
                "if (!ids.length) { pm.execution.skipRequest(); }",
            ],
            tests=standard_success("Bulk cancel"),
        ),
    ]


teardown_items = [
    follow("Restore Follower 1 to 1x Multiplier", "follower1_oms_token", "multiplier", 1),
    follow("Restore Follower 2 to 1x Multiplier", "follower2_oms_token", "multiplier", 1),
]
teardown_items += cleanup_read("Master", "master_oms_token", "master")
teardown_items += cleanup_read("Follower 1", "follower1_oms_token", "follower1")
teardown_items += cleanup_read("Follower 2", "follower2_oms_token", "follower2")
teardown_items += [
    set_balance("Restore Master Balance to 10,000 (optional admin)", "master_client_id", 10000, "Postman QA restore"),
    set_balance("Restore Follower 1 Balance to 5,000 (optional admin)", "follower1_client_id", 5000, "Postman QA restore"),
    set_balance("Restore Follower 2 Balance to 5,000 (optional admin)", "follower2_client_id", 5000, "Postman QA restore"),
]
teardown = folder(
    "6. Teardown and Restore",
    "Run after trading. Relationship and trade cleanup use trader tokens. The final three balance requests are optional and require an admin token.",
    teardown_items,
)


negative = folder(
    "7. Safe Negative and Authorization Checks",
    "Non-destructive validation checks. These replace stale bug-inducing requests that could leave invalid balances or exposure.",
    [
        item(
            "Invalid Password Is Rejected", "POST", OMS + "/_auth/login", broker_header=False,
            body={"email": "{{master_email}}", "password": "intentionally-wrong-password"},
            tests=[
                "pm.test('Invalid login rejected', () => pm.expect(pm.response.code).to.be.oneOf([400, 401, 403]));",
                "let j = {}; try { j = pm.response.json(); } catch (e) {}",
                "pm.test('No usable token issued', () => pm.expect(j.token).to.not.be.a('string'));",
            ],
        ),
        item(
            "Protected Positions Reject Missing Token", "GET", REAL + "/positions",
            tests=["pm.test('Missing token rejected', () => pm.response.to.have.status(401));"],
        ),
        item(
            "Zero-Quantity Market Order Is Rejected", "POST", REAL + "/orders", token="master_oms_token",
            body={"symbol": "{{symbol}}", "side": "BUY", "qty": 0, "type": "MARKET", "source": "postman_negative"},
            tests=["pm.test('Zero quantity rejected', () => pm.expect(pm.response.code).to.be.oneOf([400, 422]));"],
        ),
        item(
            "Unknown MAM Master Is Rejected", "POST", REAL + "/mam/follow", token="follower1_oms_token",
            body={"master_client_id": "mem_postman_does_not_exist", "method": "multiplier", "multiplier": 1},
            tests=["pm.test('Unknown master rejected', () => pm.expect(pm.response.code).to.be.oneOf([400, 404]));"],
        ),
    ],
)


collection = {
    "info": {
        "_postman_id": "terminal-blacktrader-full-v3-current-oms",
        "name": "BlackTrader Terminal — Full API Collection (Current MAM + OMS)",
        "description": (
            "Updated for https://terminal.blacktrader.com/test on 2026-11-21.\n\n"
            "The collection uses direct OMS login at /v1/oms/_auth/login, Real Hedging OMS routes, current MAM allocation fields, qty-based orders, /reduce partial closes, and sl/tp/trailing protection. "
            "The existing snake_case environment variable names are preserved. Run Auth Setup first. Trading requests create real-engine test exposure and may copy to active MAM followers; use dedicated test accounts and always run Teardown. "
            "Admin requests are optional and require separate admin credentials."
        ),
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
    },
    "item": [auth, admin, account, mam, orders, positions, teardown, negative],
    "variable": [
        {"key": "base_url", "value": "https://terminal.blacktrader.com", "type": "default"},
        {"key": "manager_display_name", "value": "mamhedgingmaster", "type": "default"},
        {"key": "manager_share_percent", "value": "50", "type": "default"},
        {"key": "request_id", "value": "", "type": "default"},
        {"key": "group_id", "value": "", "type": "default"},
        {"key": "master_position_ids_json", "value": "[]", "type": "default"},
        {"key": "follower1_position_ids_json", "value": "[]", "type": "default"},
        {"key": "follower2_position_ids_json", "value": "[]", "type": "default"},
        {"key": "master_pending_ids_json", "value": "[]", "type": "default"},
        {"key": "follower1_pending_ids_json", "value": "[]", "type": "default"},
        {"key": "follower2_pending_ids_json", "value": "[]", "type": "default"},
    ],
}


payload = json.dumps(collection, indent=2, ensure_ascii=False) + "\n"
for output in OUTPUTS:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(payload, encoding="utf-8")

print(json.dumps({
    "outputs": [str(path) for path in OUTPUTS],
    "folders": len(collection["item"]),
    "requests": sum(len(folder_["item"]) for folder_ in collection["item"]),
}, indent=2))
