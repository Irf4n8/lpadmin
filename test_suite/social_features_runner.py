#!/usr/bin/env python3
"""
BlackTrader Social-Trading Feature Suite (copy / MAM / PAMM / IB / wallets / instances)
=======================================================================================
The platform grew well beyond "follow a master": it now has four trading instances, three social modes
(Standard copy, MAM, PAMM), a referral (IB) programme, wallets and a money portal, all gated by plan modules.
This suite checks the CONTRACT of that surface.  It is read-only, except a few invalid-payload probes that must
be rejected (4xx) and must not create anything.

F1  Instances            4 instances; mode/netting flags consistent; user and admin views agree
F2  Master directories   copy / mam / pamm lists: schema, ranks, share_percent range, no duplicates
F3  Role exclusivity     a master can't follow; a follower can't become a master (reasons present, both directions)
F4  Relationship shape   follows payloads: required keys, valid instance + status values
F5  Auth enforcement     every social / money endpoint refuses anonymous callers (401/403)
F6  Money/IB/portal      wallets, portal summary, IB summary, history: reachable, well-formed
F7  Invalid writes       unknown master / bad method / negative deposit are rejected with 4xx, nothing created
F8  Admin config         instances, groups, plan modules (copytrading, mam, pamm, ib, wallet) and KYC lists

Usage:
    python test_suite/social_features_runner.py
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config.settings import BASE_URL, DEFAULT_PREFIX, DEFAULT_DOMAIN, MASTER_EMAIL
from test_suite.client import BlackTraderClient
from test_suite.netting_hedging_runner import Check

STAT_KEYS = {"growth", "curve", "weeks", "followers", "drawdown", "fund", "risk_level", "rank", "trades"}
LINK_STATUS = {"active", "ended", "closed", "pending", "paused", "processing"}
SOCIAL_MODULES = {"copytrading", "mam", "pamm", "ib", "wallet"}
FOLLOWER = f"{DEFAULT_PREFIX}1@{DEFAULT_DOMAIN}"          # follower1: unlinked, safe for rejected-write probes


def ok200(res) -> bool:
    return res["status_code"] == 200 and isinstance(res["data"], dict)


def f1_instances(c, k):
    ins = c.get_instances(MASTER_EMAIL)
    slugs = {i["slug"]: i for i in ins}
    k.true("4 instances exist (paper, paper-net, real, real-net)", set(slugs) == set(c.INSTANCES), f"(got {sorted(slugs)})")
    for s, i in slugs.items():
        k.true(f"{s}: mode matches netting flag", (i.get("mode") == "netting") == bool(i.get("netting")), f"({i.get('mode')}/{i.get('netting')})")
        k.true(f"{s}: real_money flag follows the name", bool(i.get("real_money")) == s.startswith("real"), f"({i.get('real_money')})")
        k.true(f"{s}: hedging/netting follows the -net suffix", (i.get("mode") == "netting") == s.endswith("-net"))
    adm = c.admin_get("instances")
    if k.true("admin /instances reachable", ok200(adm)):
        allrows = {i["slug"]: i for i in adm["data"].get("instances", [])}
        a = {s: i for s, i in allrows.items() if i.get("enabled") and i.get("visible")}
        spare = sorted(set(allrows) - set(a))
        k.notes.append(f"spare (disabled/hidden) instances: {spare}")
        k.true("enabled+visible admin instances equal the user's instance list", set(a) == set(slugs), f"(admin {sorted(a)})")
        k.true("admin product matches mode (…_net for netting)", all(a[s].get("product", "").endswith("_net") == (a[s].get("mode") == "netting") for s in a),
               str({s: a[s].get("product") for s in a}))


def f2_directories(c, k):
    for kind in c.SOCIAL_KINDS:
        ms = c.social_masters(MASTER_EMAIL, kind, "real")
        k.true(f"{kind}: directory returns masters", len(ms) > 0, "(empty)")
        ids = [m.get("client_id") for m in ms]
        k.true(f"{kind}: no duplicate masters", len(ids) == len(set(ids)))
        bad = [m.get("name") for m in ms if not STAT_KEYS <= set((m.get("stats") or {}).keys()) or not m.get("client_id") or not m.get("name")]
        k.true(f"{kind}: every master has id, name and full stats {sorted(STAT_KEYS)}", not bad, f"(incomplete: {bad[:4]})")
        ranks = [m["stats"]["rank"] for m in ms if "stats" in m and "rank" in m["stats"]]
        k.true(f"{kind}: ranks sorted ascending", ranks == sorted(ranks), f"({ranks[:8]})")
        odd = [m["name"] for m in ms if (m.get("stats") or {}).get("drawdown", 0) < 0 or (m.get("stats") or {}).get("followers", 0) < 0]
        k.true(f"{kind}: no negative drawdown/followers", not odd, f"({odd[:4]})")
        if kind in ("mam", "pamm"):
            sp = [m.get("share_percent") for m in ms]
            k.true(f"{kind}: share_percent present and within 0..100", all(isinstance(x, (int, float)) and 0 <= x <= 100 for x in sp), f"({sp[:8]})")
        if kind == "copy":
            kinds = {m.get("kind") for m in ms}
            k.true("copy: master kinds are copy_manager | private_master", kinds <= {"copy_manager", "private_master"}, str(kinds))
            k.notes.append(f"copy master kinds present: {sorted(kinds)}")
    a = {m["client_id"] for m in c.social_masters(MASTER_EMAIL, "copy", "real")}
    b = {m["client_id"] for m in c.social_masters(FOLLOWER, "copy", "real")}
    k.true("master directory is the same for master and follower views", a == b)


def f3_roles(c, k):
    for kind in ("mam", "pamm"):
        r = c.social_follows(MASTER_EMAIL, kind, "real")
        if k.true(f"{kind}/follows reachable for the copy master", ok200(r)):
            k.true(f"{kind}: master gets follow_blocked_reason ('can't follow another master')",
                   bool(r["data"].get("follow_blocked_reason")), f"({r['data'].get('follow_blocked_reason')!r})")
    r = c.social_follows(FOLLOWER, "mam", "real")
    if k.true("mam/follows reachable for a follower", ok200(r)):
        k.true("follower has no follow block", not r["data"].get("follow_blocked_reason"), f"({r['data'].get('follow_blocked_reason')!r})")
    # an account with an ACTIVE standard-copy link must not be able to become a master
    linked = [f for f in c.get_copy_followers(MASTER_EMAIL, "paper", active_only=True)]
    if linked:
        e = f"{linked[0]['follower_name']}@{DEFAULT_DOMAIN}"
        for kind in ("mam", "pamm"):
            r = c.social_follows(e, kind, "real")
            if ok200(r):
                k.true(f"{kind}: follower {linked[0]['follower_name']} is blocked from becoming a master",
                       bool(r["data"].get("master_blocked_reason")), f"({r['data'].get('master_blocked_reason')!r})")
    else:
        k.notes.append("no active linked follower found - follower-side block not checked")


def f4_shapes(c, k):
    r = c.social_follows(MASTER_EMAIL, "copy", "real")
    if k.true("copy/follows reachable", ok200(r)):
        links = r["data"].get("followers", [])
        k.true("copy/follows lists the master's followers", len(links) > 0, "(none)")
        need = {"follow_id", "master_client_id", "follower_client_id", "instance", "method", "multiplier", "reverse", "copy_mode", "status"}
        miss = [l.get("follow_id") for l in links if not need <= set(l)]
        k.true("every link carries the full field set", not miss, f"(incomplete: {miss[:3]})")
        k.true("link instances are valid slugs", all(l.get("instance") in c.INSTANCES for l in links), str({l.get('instance') for l in links}))
        k.true("link statuses are known", all(l.get("status") in LINK_STATUS for l in links), str({l.get('status') for l in links}))
        k.true("methods are multiplier|balance|equity", all(l.get("method") in ("multiplier", "balance", "equity") for l in links),
               str({l.get('method') for l in links}))
        k.true("copy_mode is public|private", all(l.get("copy_mode") in ("public", "private") for l in links), str({l.get('copy_mode') for l in links}))
        per = {}
        for l in links:
            per.setdefault(l["follower_client_id"], 0)
            per[l["follower_client_id"]] += 1
        k.true("one link record per follower (no duplicates)", all(v == 1 for v in per.values()), f"({sum(1 for v in per.values() if v > 1)} duplicated)")
    for kind, keys in (("mam", {"followers", "following", "is_master", "master", "follow_blocked_reason", "master_blocked_reason"}),
                       ("pamm", {"pool", "pool_history", "pool_total", "subscriptions", "is_master", "master", "follow_blocked_reason", "master_blocked_reason"})):
        r = c.social_follows(MASTER_EMAIL, kind, "real")
        if ok200(r):
            k.true(f"{kind}/follows has keys {sorted(keys)}", keys <= set(r["data"]), f"(missing {sorted(keys - set(r['data']))})")


def f5_auth(c, k):
    paths = [("real", "/copy/masters"), ("real", "/copy/follows"), ("real", "/mam/masters"), ("real", "/mam/follows"),
             ("real", "/pamm/masters"), ("real", "/pamm/follows"), ("real", "/wallets"), ("real", "/portal/summary"),
             ("real", "/ib/summary"), ("real", "/portal/transfers")]
    for inst, p in paths:
        r = c.oms(None, "GET", p, inst)
        k.true(f"anonymous GET {p} refused", r["status_code"] in (401, 403), f"(got {r['status_code']})")
    for p in ("/copy/follow", "/mam/follow", "/pamm/join", "/copy/master", "/wallets/transfer"):
        r = c.oms(None, "POST", p, "real", json={})
        k.true(f"anonymous POST {p} refused", r["status_code"] in (401, 403), f"(got {r['status_code']})")
    r = c.oms(None, "GET", "/_instances", root=True)
    k.notes.append(f"INFO anonymous /_instances answers {r['status_code']} (instance names/modes are public, like /api/config)")


def f6_money(c, k):
    for p in ("/wallets", "/wallets/history?limit=5", "/portal/summary", "/portal/history?limit=5", "/portal/transfers?limit=5",
              "/portal/payout-methods", "/ib/summary", "/ib/payouts?limit=5", "/ib/downline?limit=5"):
        r = c.oms(MASTER_EMAIL, "GET", p, "real")
        k.true(f"GET {p} -> JSON 200", ok200(r) and r["data"].get("success", True) is not False,
               f"(got {r['status_code']} {str(r['data'])[:100]})")
        if r["status_code"] >= 500:
            k.fails.append(f"5xx on GET {p}")


def f7_invalid_writes(c, k):
    before = c.social_follows(FOLLOWER, "copy", "real")["data"]
    probes = [
        ("copy follow, unknown master", "/copy/follow", {"master_client_id": "mem_doesnotexist000", "method": "multiplier", "multiplier": 1, "reverse": False, "copy_mode": "public"}),
        ("copy follow, bad method", "/copy/follow", {"master_client_id": "mem_doesnotexist000", "method": "teleport", "multiplier": 1}),
        ("copy follow, negative multiplier", "/copy/follow", {"master_client_id": "mem_doesnotexist000", "method": "multiplier", "multiplier": -3}),
        ("mam follow, unknown master", "/mam/follow", {"master_client_id": "mem_doesnotexist000", "method": "multiplier", "multiplier": 1}),
        ("pamm join, unknown master", "/pamm/join", {"master_client_id": "mem_doesnotexist000", "deposit": 10}),
        ("pamm join, negative deposit", "/pamm/join", {"master_client_id": "mem_doesnotexist000", "deposit": -10}),
        ("copy unfollow, unknown master", "/copy/unfollow", {"master_client_id": "mem_doesnotexist000"}),
    ]
    for label, path, body in probes:
        r = c.oms(FOLLOWER, "POST", path, "real", json=body)
        sc = r["status_code"]
        k.true(f"{label} rejected with 4xx", 400 <= sc < 500, f"(got {sc}: {str(r['data'])[:110]})")
        if sc >= 500:
            k.fails.append(f"SERVER ERROR {sc} on '{label}' - should be a 4xx validation error")
    after = c.social_follows(FOLLOWER, "copy", "real")["data"]
    k.true("no relationship was created by the rejected writes", before == after)
    k.true("follower1 still has no active link anywhere",
           not [l for l in c.get_copy_followers(MASTER_EMAIL, "paper", active_only=True) if l.get("follower_name") == "follower1"])


def f8_admin(c, k):
    g = c.admin_get("groups")
    if k.true("admin /groups reachable", ok200(g)):
        grp = g["data"].get("groups", [])
        k.true("a default group exists", any(x.get("is_default") for x in grp), str([x.get("group_code") for x in grp]))
        need = {"brokerage", "markup", "ib", "margin_percent", "group_code"}
        k.true("groups carry brokerage, markup, ib and margin settings", all(need <= set(x) for x in grp))
        k.true("IB levels are percentages", all(all(0 <= v <= 100 for v in (x.get("ib") or {}).get("levels", [])) for x in grp))
    cf = c.admin_get("config")
    if k.true("admin /config reachable", ok200(cf)):
        pm = cf["data"].get("plan_modules", {})
        k.true("plans defined: free, basic, premium, pro", {"free", "basic", "premium", "pro"} <= set(pm), f"({sorted(pm)})")
        for plan in ("premium", "pro"):
            miss = SOCIAL_MODULES - set(pm.get(plan, []))
            k.true(f"{plan} plan includes {sorted(SOCIAL_MODULES)}", not miss, f"(missing {sorted(miss)})")
        for plan in ("free", "basic"):
            k.true(f"{plan} plan has no social-trading modules", not (SOCIAL_MODULES & set(pm.get(plan, []))), f"({sorted(SOCIAL_MODULES & set(pm.get(plan, [])))})")
    for path in ("deposits", "withdrawals", "kyc"):
        r = c.admin_get(path)
        k.true(f"admin /{path} reachable", ok200(r) and r["data"].get("success", True) is not False, f"(got {r['status_code']})")
    mem = c.admin_get("members", {"limit": 1})
    if ok200(mem):
        row = mem["data"]["members"][0] if mem["data"].get("members") else {}
        k.true("member rows expose book, plan, group_code, allowed_modules", {"book", "plan", "group_code", "allowed_modules"} <= set(row), f"(keys {sorted(row)})")
        k.notes.append(f"member row keys: {sorted(row)}")
        bal = {m.get("email"): (m.get("balances") or {}) for m in mem["data"]["members"]}
        k.true("balances are keyed per instance", all(set(b) <= set(c.INSTANCES) for b in bal.values()), str(bal)[:120])


SCENARIOS = [("F1 Instances", f1_instances), ("F2 Master directories", f2_directories), ("F3 Role exclusivity", f3_roles),
             ("F4 Relationship shape", f4_shapes), ("F5 Auth enforcement", f5_auth), ("F6 Money / IB / portal reads", f6_money),
             ("F7 Invalid writes rejected", f7_invalid_writes), ("F8 Admin config", f8_admin)]


def main() -> int:
    ap = argparse.ArgumentParser(description="Social-trading feature suite (read-mostly)")
    ap.add_argument("--only", default="", help="e.g. F1,F7")
    ap.add_argument("--start", default=None); ap.add_argument("--end", default=None); ap.add_argument("--instance", default=None)  # dashboard compat
    args = ap.parse_args()
    wanted = {w.strip().upper() for w in args.only.split(",") if w.strip()}
    c = BlackTraderClient(BASE_URL)
    print("=" * 80 + "\n SOCIAL-TRADING FEATURE SUITE (copy / MAM / PAMM / IB / wallets / instances)\n" + "=" * 80)
    results: List[Dict[str, Any]] = []
    for name, fn in SCENARIOS:
        if wanted and name.split()[0].upper() not in wanted:
            continue
        print(f"\n[{name}]")
        chk = Check(name)
        try:
            fn(c, chk)
        except Exception as e:
            chk.fails.append(f"EXC {type(e).__name__}: {e}")
        results.append(chk.result())
    out = BASE_DIR / "reports" / "evidence"; out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    (out / f"social_features_evidence_{ts}.json").write_text(json.dumps(
        {"suite": "Social-trading features", "timestamp": datetime.now(timezone.utc).isoformat(), "results": results}, indent=2), encoding="utf-8")
    L = ["# Social-Trading Feature Evidence Report", "", f"**Generated:** {datetime.now(timezone.utc).isoformat()}", "",
         "| Scenario | Result | Detail |", "| :--- | :---: | :--- |"]
    for r in results:
        detail = "; ".join(r["failures"]) if r["failures"] else f"{len(r['notes'])} checks passed"
        L.append(f"| {r['name']} | {'✅' if r['status'] == 'PASS' else '❌'} {r['status']} | {detail.replace('|', '/')} |")
    L += ["", "## Every check", ""]
    for r in results:
        L += [f"### {r['name']}"] + [f"- ✅ {n}" for n in r["notes"]] + [f"- ❌ {f}" for f in r["failures"]] + [""]
    mp = out / f"social_features_evidence_{ts}.md"
    mp.write_text("\n".join(L) + "\n", encoding="utf-8")
    failed = sum(1 for r in results if r["status"] != "PASS")
    print("\n" + "=" * 80 + f"\n SUMMARY: {len(results) - failed}/{len(results)} scenarios passed\n Report : {mp}\n" + "=" * 80)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
