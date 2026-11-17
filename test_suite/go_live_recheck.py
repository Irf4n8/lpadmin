#!/usr/bin/env python3
"""Targeted re-checks of the go-live spec failures that were unexplained (R023/R024, R003, F018/P009, C015/R018)."""
import sys, time, json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import test_suite.go_live_spec_runner as g
from test_suite.go_live_spec_runner import *  # noqa

OUT = {}
def now(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
def copies_of(e, mid): return [o for o in orders(e) if (o.get("copy_ref") or "").lstrip("-") == mid]
def flat_check():
    bad = [f for f in ALL if pos(f) or pend(f)]
    return bad

def main():
    for m in c.get_admin_members(): g.MEMBERS[m.get("email")] = m.get("member_id")
    g.MID = c.get_copy_followers(M, I)[0]["master_client_id"]
    # ---- A: 1 order to 100 followers, three times ----
    A = []
    for rnd in range(3):
        clean(); clean()
        dirty = flat_check()
        r = buy(0.01); mid = oid_of(r)
        last = -1
        for _ in range(30):
            time.sleep(3)
            got = [f for f in ALL if any(o.get("state") == "FILLED" for o in copies_of(f, mid))]
            if len(got) == last and len(got) == 100: break
            last = len(got)
        got = {f for f in ALL if any(o.get("state") == "FILLED" for o in copies_of(f, mid))}
        miss = [f.split("@")[0] for f in ALL if f not in got]
        rej = [(f.split("@")[0], [(o["state"], o.get("requested_qty")) for o in copies_of(f, mid)]) for f in ALL if f not in got][:5]
        A.append({"round": rnd + 1, "dirty_before": len(dirty), "master_http": r["status_code"], "copied": len(got), "missing": miss[:12], "sample": rej})
        print(f"[A{rnd+1}] dirty-before={len(dirty)} master={r['status_code']} copied {len(got)}/100 missing {miss[:10]} sample {rej[:2]}", flush=True)
        clean(); 
    OUT["R023_R024"] = A
    # ---- B: burst of 10 ----
    clean(); t0 = time.time()
    with ThreadPoolExecutor(10) as ex: rr = list(ex.map(lambda _: buy(), range(10)))
    B1 = [(x["status_code"], str(x["data"])[:90] if x["status_code"] != 200 else "") for x in rr]
    print(f"[B1] concurrent x10 in {time.time()-t0:.1f}s: {sum(x[0]==200 for x in B1)} accepted; refusals {sorted({b[1] for b in B1 if b[0]!=200})}", flush=True)
    time.sleep(10); clean()
    t0 = time.time(); B2 = []
    for _ in range(10):
        x = buy(); B2.append((x["status_code"], str(x["data"])[:90] if x["status_code"] != 200 else "")); time.sleep(0.1)
    print(f"[B2] sequential x10 (0.1 s gap) in {time.time()-t0:.1f}s: {sum(x[0]==200 for x in B2)} accepted; refusals {sorted({b[1] for b in B2 if b[0]!=200})}", flush=True)
    ok = sum(x[0] == 200 for x in B2); time.sleep(12)
    cnt = [len(pos(f)) for f in F]
    print(f"     followers positions (want {ok}): {sorted(set(cnt))}", flush=True)
    OUT["R003"] = {"concurrent": B1, "sequential": B2, "follower_positions": cnt}
    clean()
    # ---- C: under-funded follower ----
    f2 = F[1]; t0 = now()
    s = setbal(f2, 1); r = buy(0.5); mid = oid_of(r); time.sleep(15)
    rows = {f.split("@")[0]: (netq(f), [(o["state"], o.get("requested_qty"), o.get("reject_reason") or o.get("reason") or "") for o in copies_of(f, mid)]) for f in F}
    print(f"[C] follower2 balance=1 (HTTP {s}), master 0.5 BTC HTTP {r['status_code']}", flush=True)
    for k, v in rows.items(): print("    ", k, v, flush=True)
    OUT["F018"] = {"master": r["status_code"], "rows": rows}
    setbal(f2, 100000000); clean()
    # ---- D: unfollow with an open position ----
    f = F[0]; buy(); wait(lambda: pos(f)); before = len(pos(f)); t0 = now()
    u = c.unfollow_master(f, g.MID, I); time.sleep(3)
    after = len(pos(f)); h = [(x.get("exit_source"), x.get("qty")) for x in hist(f) if x["executed_at"] >= t0[:19]]
    print(f"[D] position before unfollow {before}, unfollow HTTP {u['status_code']}, after {after}; history rows since: {h[:3]}", flush=True)
    OUT["C015"] = {"before": before, "after": after, "history": h[:3]}
    follow(f); clean()
    out = ROOT / "reports" / "evidence" / f"go_live_recheck_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(OUT, indent=2, default=str)); print("[*] evidence:", out)

main()
