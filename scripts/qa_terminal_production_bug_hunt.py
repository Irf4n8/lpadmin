"""Targeted production-facing defect hunt for terminal.blacktrader.com/test.

Uses only the three dedicated test accounts authorized by the user. Passwords and
bearer tokens are never written to evidence. All state-changing cases clean up.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "terminal_production_bug_hunt_20261121"
OUT.mkdir(parents=True, exist_ok=True)
REPORT = ROOT / "TERMINAL_PRODUCTION_BUG_HUNT_REPORT.md"
BASE = "https://terminal.blacktrader.com/test"
AUTH = BASE + "/v1/oms/_auth"
REAL = BASE + "/v1/oms/real"
MASTER = "mamhm@mailinator.com"
F1 = "mamhf1@mailinator.com"
F2 = "mamhf2@mailinator.com"
ACCOUNTS = [MASTER, F1, F2]
MASTER_ID = "mem_6cf38c1f751cbd1699"
SYMBOL = "BLACK:BTCUSD"
PASSWORD = os.environ.get("TERMINAL_MAM_PASSWORD", "")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_json(response: requests.Response) -> dict:
    try:
        body = response.json()
        return body if isinstance(body, dict) else {"value": body}
    except ValueError:
        return {"text": response.text[:500]}


class BugHunt:
    def __init__(self) -> None:
        if not PASSWORD:
            raise RuntimeError("TERMINAL_MAM_PASSWORD is required")
        self.tokens: dict[str, str] = {}
        self.results: list[dict] = []
        self.original_master: dict = {}

    def login_token(self, email: str) -> str:
        response = requests.post(AUTH + "/login", json={"email": email, "password": PASSWORD}, timeout=20)
        body = safe_json(response)
        token = body.get("token")
        if response.status_code != 200 or body.get("success") is not True or not token:
            raise RuntimeError(f"login failed for {email}: HTTP {response.status_code}")
        return token

    def login_all(self) -> None:
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            values = list(pool.map(self.login_token, ACCOUNTS))
        self.tokens = dict(zip(ACCOUNTS, values))

    def call(self, email: str, method: str, endpoint: str, payload=None, token: str | None = None) -> dict:
        response = requests.request(
            method,
            REAL + "/" + endpoint.lstrip("/"),
            headers={
                "Authorization": "Bearer " + (token or self.tokens[email]),
                "X-Broker-ID": "real",
            },
            json=payload,
            timeout=30,
        )
        return {
            "http": response.status_code,
            "body": safe_json(response),
            "headers": {
                key.lower(): value
                for key, value in response.headers.items()
                if key.lower() in {
                    "cache-control", "pragma", "expires", "access-control-allow-origin",
                    "access-control-allow-credentials", "vary", "content-security-policy",
                    "x-frame-options", "referrer-policy",
                }
            },
        }

    def check(self, case_id: str, title: str, defect_id: str, severity: str, fn) -> None:
        started = now()
        try:
            passed, actual, expected = fn()
            status = "PASS" if passed else "FAIL"
        except Exception as exc:  # evidence must retain unexpected blockers
            status = "BLOCKED"
            actual = {"error": f"{type(exc).__name__}: {exc}"}
            expected = "Case executes and returns a deterministic assertion."
        row = {
            "id": case_id,
            "title": title,
            "expected": expected,
            "actual": actual,
            "status": status,
            "severity": severity if status == "FAIL" else "—",
            "defect_id": defect_id if status == "FAIL" else "—",
            "started_at": started,
            "finished_at": now(),
        }
        self.results.append(row)
        (OUT / "results.json").write_text(json.dumps(self.results, indent=2), encoding="utf-8")
        print(f"[{status}] {case_id}: {title}", flush=True)

    def link(self, email: str) -> dict:
        response = self.call(email, "GET", "mam/follows")
        if response["http"] != 200:
            raise RuntimeError(f"relationship read failed for {email}: {response['http']}")
        return response["body"]

    def active_follow(self, email: str) -> dict:
        rows = [
            row for row in self.link(email).get("following", [])
            if row.get("status") == "active" and row.get("master_client_id") == MASTER_ID
        ]
        if len(rows) != 1:
            raise RuntimeError(f"expected one active relationship for {email}, found {len(rows)}")
        return rows[0]

    def configure(self, email: str, method="multiplier", multiplier=1) -> dict:
        return self.call(email, "POST", "mam/follow", {
            "master_client_id": MASTER_ID,
            "method": method,
            "multiplier": multiplier,
        })

    def positions(self, email: str) -> dict:
        response = self.call(email, "GET", "positions")
        if response["http"] != 200:
            raise RuntimeError(f"positions read failed for {email}: {response['http']}")
        return response["body"]

    def cleanup(self) -> None:
        # Parent closes first; any remaining children are then closed directly.
        for position in self.positions(MASTER).get("positions", []):
            self.call(MASTER, "POST", f"positions/{position['market_order_id']}/squareoff", {})
        time.sleep(0.7)
        for email in ACCOUNTS:
            for position in self.positions(email).get("positions", []):
                self.call(email, "POST", f"positions/{position['market_order_id']}/squareoff", {})
            orders = self.call(email, "GET", "orders")["body"].get("orders", [])
            for order in orders:
                if order.get("state") in {"PENDING", "OPEN", "NEW"}:
                    self.call(email, "DELETE", f"orders/{order['order_id']}")
        time.sleep(0.5)

    def preflight(self) -> None:
        self.cleanup()
        self.configure(F1)
        self.configure(F2)
        master_links = self.link(MASTER)
        self.original_master = dict(master_links.get("master") or {})

    def auth_cases(self) -> None:
        def logout_invalidation():
            token = self.login_token(F2)
            before = self.call(F2, "GET", "positions", token=token)
            logout = requests.post(AUTH + "/logout", headers={"Authorization": "Bearer " + token}, timeout=20)
            after = self.call(F2, "GET", "positions", token=token)
            passed = before["http"] == 200 and logout.status_code == 204 and after["http"] == 401
            return passed, {"before": before["http"], "logout": logout.status_code, "after": after["http"]}, "A logged-out session token must immediately return HTTP 401."

        self.check("PROD-AUTH-001", "Logout immediately invalidates the current OMS session", "TERM-AUTH-001", "High", logout_invalidation)

        def other_session_survives():
            first = self.login_token(F2)
            second = self.login_token(F2)
            requests.post(AUTH + "/logout", headers={"Authorization": "Bearer " + first}, timeout=20)
            first_after = self.call(F2, "GET", "positions", token=first)
            second_after = self.call(F2, "GET", "positions", token=second)
            requests.post(AUTH + "/logout", headers={"Authorization": "Bearer " + second}, timeout=20)
            passed = first_after["http"] == 401 and second_after["http"] == 200
            return passed, {"logged_out_session": first_after["http"], "independent_session": second_after["http"]}, "Logout revokes only the selected session and does not terminate another valid login."

        self.check("PROD-AUTH-002", "Logging out one device does not corrupt another valid session", "TERM-AUTH-002", "High", other_session_survives)

        def admin_boundary():
            response = requests.get(
                BASE + "/admin/api/members",
                headers={"Authorization": "Bearer " + self.tokens[MASTER]},
                timeout=20,
            )
            return response.status_code in (401, 403), {"http": response.status_code}, "A trader token must not authorize client-admin member APIs."

        self.check("PROD-AUTH-003", "Trader token cannot access client-admin member data", "TERM-AUTH-003", "Critical", admin_boundary)

    def mam_validation_cases(self) -> None:
        def invalid_method():
            before = self.active_follow(F1)
            response = self.configure(F1, method="not_a_real_allocation_method", multiplier=1)
            after = self.active_follow(F1)
            self.configure(F1)
            unchanged = after.get("method") == before.get("method") and after.get("multiplier") == before.get("multiplier")
            passed = response["http"] in (400, 422) and unchanged
            return passed, {
                "http": response["http"],
                "stored_method": after.get("method"),
                "stored_multiplier": after.get("multiplier"),
                "relationship_unchanged": unchanged,
            }, "Unknown allocation methods must be rejected and must not alter the active relationship."

        self.check("PROD-MAM-VALID-001", "Reject an unknown MAM allocation method", "TERM-MAM-003", "High", invalid_method)

        for label, value in (("ZERO", 0), ("NEGATIVE", -5)):
            def invalid_multiplier(value=value):
                before = self.active_follow(F1)
                response = self.configure(F1, multiplier=value)
                after = self.active_follow(F1)
                self.configure(F1)
                unchanged = after.get("multiplier") == before.get("multiplier")
                passed = response["http"] in (400, 422) and unchanged
                return passed, {
                    "submitted_multiplier": value,
                    "http": response["http"],
                    "stored_method": after.get("method"),
                    "stored_multiplier": after.get("multiplier"),
                    "relationship_unchanged": unchanged,
                }, "A multiplier less than or equal to zero must be rejected without silently changing it to another value."

            self.check(
                f"PROD-MAM-VALID-{label}",
                f"Reject {label.lower()} MAM multiplier",
                "TERM-MAM-004",
                "High",
                invalid_multiplier,
            )

        def invalid_multiplier_type():
            before = self.active_follow(F1)
            response = self.configure(F1, multiplier="two")
            after = self.active_follow(F1)
            self.configure(F1)
            unchanged = after.get("multiplier") == before.get("multiplier")
            return response["http"] in (400, 422) and unchanged, {
                "http": response["http"], "stored_multiplier": after.get("multiplier"), "relationship_unchanged": unchanged,
            }, "A nonnumeric multiplier must be rejected without altering the relationship."

        self.check("PROD-MAM-VALID-TYPE", "Reject a nonnumeric MAM multiplier", "TERM-MAM-005", "High", invalid_multiplier_type)

        def fee_bounds():
            if not self.original_master:
                raise RuntimeError("master configuration not available")
            attempts = []
            for share in (-1, 101):
                response = self.call(MASTER, "POST", "mam/master", {
                    "display_name": self.original_master["display_name"], "share_percent": share,
                })
                attempts.append({"share_percent": share, "http": response["http"]})
            current = self.link(MASTER).get("master") or {}
            passed = all(row["http"] in (400, 422) for row in attempts) and current.get("share_percent") == self.original_master.get("share_percent")
            return passed, {"attempts": attempts, "stored_share_percent": current.get("share_percent")}, "Performance-share values outside 0–100 must be rejected without changing the saved fee."

        self.check("PROD-MAM-FEE-001", "Reject manager performance-share values outside 0–100", "TERM-MAM-006", "Critical", fee_bounds)

    def pending_idempotency(self) -> None:
        def duplicate_pending():
            request_id = "pending_retry_" + uuid.uuid4().hex[:16]
            group_id = "pending_group_" + uuid.uuid4().hex[:16]
            payload = {
                "symbol": SYMBOL,
                "side": "BUY",
                "qty": 0.01,
                "type": "LIMIT",
                "price": 1,
                "request_id": request_id,
                "group_id": group_id,
                "source": "qa",
                "tag": "PRODUCTION_BUG_HUNT",
            }
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(pool.map(lambda _: self.call(MASTER, "POST", "orders/pending", payload), range(2)))
            time.sleep(1)
            counts = {}
            for email in ACCOUNTS:
                orders = self.call(email, "GET", "orders")["body"].get("orders", [])
                counts[email] = len([row for row in orders if row.get("group_id") == group_id and row.get("state") in {"PENDING", "OPEN", "NEW"}])
            accepted = sum(row["http"] == 200 and row["body"].get("success") is True for row in responses)
            self.cleanup()
            passed = accepted == 1 and all(count == 1 for count in counts.values())
            return passed, {
                "accepted_requests": accepted,
                "working_order_counts": counts,
                "request_identity_reused": True,
            }, "Two concurrent deliveries with the same request_id/group_id must produce exactly one master order and one child order per follower."

        self.check("PROD-ORDER-IDEMPOTENCY-PENDING", "Concurrent retry cannot duplicate a pending MAM order", "TERM-MAM-002", "Critical", duplicate_pending)

    def web_security_cases(self) -> None:
        def cors_policy():
            origin = "https://attacker.invalid"
            response = requests.options(
                REAL + "/positions",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "authorization,x-broker-id",
                },
                timeout=20,
            )
            allow_origin = response.headers.get("Access-Control-Allow-Origin", "")
            allow_credentials = response.headers.get("Access-Control-Allow-Credentials", "")
            unsafe = allow_origin in {"*", origin} and allow_credentials.lower() == "true"
            return not unsafe, {
                "http": response.status_code,
                "allow_origin": allow_origin,
                "allow_credentials": allow_credentials,
                "allow_headers": response.headers.get("Access-Control-Allow-Headers", ""),
            }, "The API must not grant credentialed cross-origin access to an arbitrary origin."

        self.check("PROD-WEB-CORS-001", "Arbitrary origins cannot make credentialed OMS requests", "TERM-SEC-002", "Critical", cors_policy)

        def sensitive_cache_headers():
            response = self.call(MASTER, "GET", "positions")
            cache_control = response["headers"].get("cache-control", "").lower()
            protected = "no-store" in cache_control
            return protected, {"http": response["http"], "response_headers": response["headers"]}, "Authenticated positions and balance data must return Cache-Control: no-store."

        self.check("PROD-WEB-CACHE-001", "Authenticated financial data is marked no-store", "TERM-SEC-003", "Medium", sensitive_cache_headers)

        def frame_headers():
            response = requests.get(BASE + "/home/dashboard", allow_redirects=False, timeout=20)
            csp = response.headers.get("Content-Security-Policy", "")
            xfo = response.headers.get("X-Frame-Options", "")
            protected = bool(xfo.strip()) or "frame-ancestors" in csp.lower()
            return protected, {
                "http": response.status_code,
                "content_security_policy": csp,
                "x_frame_options": xfo,
                "location": response.headers.get("Location", ""),
            }, "Trading pages must send X-Frame-Options or CSP frame-ancestors to prevent UI redressing."

        self.check("PROD-WEB-FRAME-HEADERS", "Trading dashboard sends anti-framing headers", "TERM-SEC-004", "High", frame_headers)

    def browser_clickjacking(self) -> None:
        def run():
            try:
                from playwright.sync_api import sync_playwright
            except ImportError as exc:
                raise RuntimeError("Playwright unavailable") from exc
            token = None
            result = {}
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(viewport={"width": 1440, "height": 1000})
                page = context.new_page()
                page.goto(BASE + "/home/login", wait_until="domcontentloaded", timeout=30000)
                page.locator('input[type="email"]').fill(MASTER)
                page.locator('input[type="password"]').fill(PASSWORD)
                with page.expect_response(lambda r: "/v1/oms/_auth/login" in r.url, timeout=30000) as response_info:
                    page.locator('button[type="submit"]').click()
                login_response = response_info.value
                login_body = login_response.json()
                token = login_body.get("token")
                page.wait_for_url("**/home/dashboard", timeout=30000)
                top_dashboard_url = page.url
                attacker_html = (
                    "data:text/html,<html><body><h1>Attacker origin</h1>"
                    "<iframe id='target' src='https://terminal.blacktrader.com/test/home/dashboard' "
                    "style='width:1300px;height:850px;opacity:0.99'></iframe></body></html>"
                )
                page.goto(attacker_html, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(6000)
                target_frames = [frame for frame in page.frames if "terminal.blacktrader.com" in frame.url]
                frame_url = target_frames[0].url if target_frames else ""
                frame_text = ""
                if target_frames:
                    try:
                        frame_text = target_frames[0].locator("body").inner_text(timeout=5000)[:1200]
                    except Exception:
                        frame_text = ""
                dashboard_rendered = bool(target_frames and "/home/dashboard" in frame_url and ("MAM" in frame_text or "Trade" in frame_text or "BTCUSD" in frame_text))
                page.screenshot(path=str(OUT / "clickjacking_dashboard.png"), full_page=True)
                result = {
                    "login_http": login_response.status,
                    "authenticated_top_level_dashboard": "/home/dashboard" in top_dashboard_url,
                    "cross_origin_frame_url": frame_url,
                    "dashboard_content_rendered_in_frame": dashboard_rendered,
                    "frame_text_markers": {
                        "mam": "MAM" in frame_text,
                        "trade": "Trade" in frame_text,
                        "btcusd": "BTCUSD" in frame_text,
                    },
                    "screenshot": "clickjacking_dashboard.png",
                }
                browser.close()
            if token:
                requests.post(AUTH + "/logout", headers={"Authorization": "Bearer " + token}, timeout=20)
            return not result["dashboard_content_rendered_in_frame"], result, "An authenticated terminal dashboard must be blocked when embedded by an unrelated origin."

        self.check("PROD-WEB-CLICKJACK-001", "Authenticated dashboard cannot be framed by another origin", "TERM-SEC-004", "High", run)

    def final_state(self) -> None:
        self.cleanup()
        self.configure(F1)
        self.configure(F2)
        if self.original_master:
            self.call(MASTER, "POST", "mam/master", {
                "display_name": self.original_master["display_name"],
                "share_percent": self.original_master["share_percent"],
            })
        positions = {email: self.positions(email).get("count") for email in ACCOUNTS}
        relationships = {
            email: {"method": self.active_follow(email).get("method"), "multiplier": self.active_follow(email).get("multiplier")}
            for email in (F1, F2)
        }
        state = {"positions": positions, "relationships": relationships, "master": self.link(MASTER).get("master")}
        (OUT / "final_state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
        good = all(value == 0 for value in positions.values()) and all(
            row == {"method": "multiplier", "multiplier": 1} for row in relationships.values()
        )
        self.check(
            "PROD-FINAL-001", "Final cleanup leaves all accounts flat and follower settings restored",
            "TERM-CLEANUP-001", "Critical", lambda: (good, state, "All three accounts are flat; both followers are active at multiplier 1; manager configuration is restored."),
        )

    def report(self) -> None:
        counts = Counter(row["status"] for row in self.results)
        defect_rows = [row for row in self.results if row["status"] == "FAIL"]
        unique = {}
        for row in defect_rows:
            unique.setdefault(row["defect_id"], row)

        def esc(value) -> str:
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            return str(value).replace("|", "\\|").replace("\n", "<br>")

        lines = [
            "# Terminal Production Bug Hunt Report",
            "",
            f"**Environment:** `{BASE}`  ",
            f"**Executed:** {now()}  ",
            "**Scope:** Dedicated Real Hedging MAM accounts; authentication, authorization, MAM validation, pending-order idempotency, browser framing, CORS and cache controls.",
            "",
            "## Summary",
            "",
            f"- Executed: **{len(self.results)}**",
            f"- PASS: **{counts.get('PASS', 0)}**",
            f"- FAIL: **{counts.get('FAIL', 0)}**",
            f"- BLOCKED: **{counts.get('BLOCKED', 0)}**",
            f"- Unique defects in this run: **{len(unique)}**",
            "- A repeated reproduction of the same root cause is counted once.",
            "",
            "## Unique Defects",
            "",
        ]
        if unique:
            for defect_id, row in unique.items():
                lines.append(f"- **{defect_id} — {row['severity']}:** {row['title']}. Actual: {esc(row['actual'])}")
        else:
            lines.append("- No new defect reproduced in this run.")
        lines += [
            "",
            "## Test Case Execution Table",
            "",
            "| TC ID | Test Case Description | Pre-Conditions | Test Steps | Test Data | Expected Result | Actual Result | Status | Severity | Defect ID | Remarks |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---: | :---: | :---: | :--- |",
        ]
        for row in self.results:
            lines.append("| " + " | ".join(map(esc, [
                row["id"], row["title"],
                "Authorized dedicated test accounts; Real Hedging; baseline flat and active MAM links.",
                "Prepare the case state; execute the named API or browser behavior; read back server state; assert the production invariant; restore state.",
                "mamhm, mamhf1 and mamhf2; BLACK:BTCUSD; terminal.blacktrader.com/test.",
                row["expected"], row["actual"], row["status"], row["severity"], row["defect_id"],
                "Evidence: reports/terminal_production_bug_hunt_20261121/results.json",
            ])) + " |")
        lines += [
            "",
            "## Evidence and Safety",
            "",
            "- `reports/terminal_production_bug_hunt_20261121/results.json`",
            "- `reports/terminal_production_bug_hunt_20261121/final_state.json`",
            "- `reports/terminal_production_bug_hunt_20261121/clickjacking_dashboard.png` when the browser case executes.",
            "- Passwords and bearer tokens are not written to evidence.",
            "- Account balances retain genuine test P&L; configuration and open-order state are restored.",
        ]
        REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    qa = BugHunt()
    try:
        qa.login_all()
        qa.preflight()
        qa.auth_cases()
        qa.mam_validation_cases()
        qa.pending_idempotency()
        qa.web_security_cases()
        qa.browser_clickjacking()
    finally:
        try:
            qa.final_state()
        finally:
            qa.report()
    counts = Counter(row["status"] for row in qa.results)
    print(json.dumps({"report": str(REPORT), "counts": counts, "results": str(OUT / "results.json")}, default=dict, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
