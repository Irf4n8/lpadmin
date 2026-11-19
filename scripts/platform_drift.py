#!/usr/bin/env python3
"""Daily platform drift check (read-only).

The BlackTrader platform ships changes every day. This takes a fingerprint of everything the suite depends on
(front-end asset hashes, admin version string, API response shapes, symbol list, instances, admin config),
compares it with the previous snapshot and writes a report to reports/platform_drift/.

    python scripts/platform_drift.py            # snapshot + diff against the latest earlier snapshot
    python scripts/platform_drift.py --quiet    # print only the verdict line

Exit code 0 = no change, 1 = platform changed (read the report), 2 = the check itself failed.
It places no orders and writes nothing to the platform.
"""
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import BASE_URL, MASTER_EMAIL  # noqa: E402
from test_suite.client import BlackTraderClient  # noqa: E402

OUT = ROOT / "reports" / "platform_drift"
INSTANCE = "real"


def shape(v, depth=0):
    """Reduce a JSON value to its structure (key names and types), so data changes are not drift."""
    if isinstance(v, dict):
        if depth >= 3:
            return "object"
        return {k: shape(x, depth + 1) for k, x in sorted(v.items())}
    if isinstance(v, list):
        if not v:
            return []
        items = v[:50]
        if all(isinstance(i, dict) for i in items):
            # union of the fields over several rows, so one row that lacks an optional field is not "drift"
            merged = {}
            for i in items:
                for k, x in i.items():
                    sh = shape(x, depth + 1)
                    if k not in merged or merged[k] == "null":
                        merged[k] = sh
            return [dict(sorted(merged.items()))]
        return [shape(v[0], depth + 1)]
    return type(v).__name__ if v is not None else "null"


def sha(b):
    return hashlib.sha256(b).hexdigest()[:16]


def take(c):
    s = {"taken_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "base_url": BASE_URL}
    get = lambda p: c.request_with_retry("GET", BASE_URL + p)

    # front-end fingerprints
    fp = {}
    for p in ("/assets/app.js", "/assets/style.css"):
        r = get(p)
        fp[p] = {"status": r.status_code, "bytes": len(r.content), "sha": sha(r.content)}
    s["frontend"] = fp

    # admin panel is a Next.js app: the build id and chunk file names change on every deploy
    try:
        page = get("/blackadmin")
        srcs = re.findall(r'<script[^>]+src="([^"]+)"', page.text)
        m = re.search(r"/_next/static/([^/]+)/_buildManifest\.js", page.text)
        s["admin_build_id"] = m.group(1) if m else None
        s["admin_chunks"] = sorted(x.rsplit("/", 1)[-1] for x in srcs if "/chunks/" in x)
    except Exception as e:  # noqa: BLE001
        s["admin_build_error"] = str(e)[:100]

    # API shapes
    api = {}
    def probe(name, fn):
        try:
            r = fn()
            api[name] = {"status": r["status_code"], "shape": shape(r["data"]) if isinstance(r["data"], (dict, list)) else "non-json"}
        except Exception as e:  # noqa: BLE001
            api[name] = {"status": "error", "shape": str(e)[:80]}
    f1 = "follower1@mailinator.com"
    for path in ("/positions", "/orders", "/history", "/wallets", "/portal/summary", "/portal/documents", "/portal/methods",
                 "/portal/payout-methods", "/portal/withdrawals", "/portal/transfers", "/copy/follows"):
        probe("oms" + path, lambda p=path: c.oms(f1 if "copy" not in p else MASTER_EMAIL, "GET", p, instance=INSTANCE))
    for path in ("config", "members", "deposits", "withdrawals", "kyc"):
        probe("admin/" + path, lambda p=path: c.admin_get(p, {"limit": 50}))
    s["api"] = api

    # instances and symbols
    try:
        inst = c.oms(f1, "GET", "/_instances", instance=INSTANCE, root=True)["data"].get("instances", [])
        s["instances"] = sorted((i.get("slug"), i.get("mode"), bool(i.get("real_money"))) for i in inst)
    except Exception as e:  # noqa: BLE001
        s["instances_error"] = str(e)[:100]
    try:
        cfg = c.admin_get("config")["data"]
        s["plan_modules"] = {k: sorted(v) for k, v in sorted(cfg.get("plan_modules", {}).items())}
        s["config_keys"] = sorted(cfg)
    except Exception as e:  # noqa: BLE001
        s["config_error"] = str(e)[:100]
    return s


def flat(d, prefix=""):
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(flat(v, f"{prefix}{k}."))
    elif isinstance(d, list) and d and all(isinstance(x, (dict, list)) for x in d):
        out[prefix.rstrip(".")] = json.dumps(d, sort_keys=True)
    else:
        out[prefix.rstrip(".")] = json.dumps(d, sort_keys=True)
    return out


def diff(old, new):
    ignore = {"taken_at"}
    a, b = flat(old), flat(new)
    rows = []
    for k in sorted(set(a) | set(b)):
        if k in ignore:
            continue
        if k not in a:
            rows.append(("added", k, None, b[k]))
        elif k not in b:
            rows.append(("removed", k, a[k], None))
        elif a[k] != b[k]:
            rows.append(("changed", k, a[k], b[k]))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        snap = take(BlackTraderClient(max_workers=4))
    except Exception as e:  # noqa: BLE001
        print(f"DRIFT CHECK FAILED: {e}")
        return 2
    prev_files = sorted(OUT.glob("snapshot_*.json"))
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    (OUT / f"snapshot_{stamp}.json").write_text(json.dumps(snap, indent=1, sort_keys=True))
    if not prev_files:
        print(f"Baseline saved ({len(snap['api'])} API shapes, admin build {snap.get('admin_build_id')}). Nothing to compare yet.")
        return 0
    old = json.loads(prev_files[-1].read_text())
    rows = diff(old, snap)
    if not rows:
        print(f"NO CHANGE since {old['taken_at']} (admin build {snap.get('admin_build_id')}).")
        return 0
    lines = [f"# Platform drift {snap['taken_at']}", f"Compared with {old['taken_at']}. {len(rows)} difference(s).", ""]
    for kind, key, o, n in rows:
        lines.append(f"- **{kind}** `{key}`" + (f": `{(o or '')[:140]}` -> `{(n or '')[:140]}`" if kind == "changed" else ""))
    (OUT / f"drift_{stamp}.md").write_text("\n".join(lines))
    print(f"PLATFORM CHANGED: {len(rows)} difference(s). Report: reports/platform_drift/drift_{stamp}.md")
    if not args.quiet:
        print("\n".join(lines[3:23]))
    return 1


if __name__ == "__main__":
    sys.exit(main())
