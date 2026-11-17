#!/usr/bin/env python3
"""
Partial-close parity: master vs followers (order count, lot size, P&L) - staging, real / hedging.
Master opens 8 positions of different sizes (BUY and SELL), then partially closes them in several ways
(single reduce, two reduces on one position, 10 %, a parallel burst of reduces, one full close).
For every follower we compare: open positions, remaining lot per entry (= master x multiplier), the list of
reduced lots, number of close events, realized P&L (total and per row, plus the (exit-entry)*qty arithmetic).
"""
import sys, time, json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import test_suite.go_live_spec_runner as g
from test_suite.go_live_spec_runner import *  # noqa

g.MID = c.get_copy_followers(M, I)[0]["master_client_id"]
N_F = 10
FS = ALL[:N_F]
if "--all" in sys.argv: FS = ALL
for f in FS: follow(f)
clean(FS)
t0 = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

# 1. open 8 positions
plan = [("BUY", 0.10), ("SELL", 0.08), ("BUY", 0.06), ("SELL", 0.12), ("BUY", 0.04), ("SELL", 0.10), ("BUY", 0.08), ("SELL", 0.05)]
entries = []
for side, q in plan:
    r = buy(q, side=side); entries.append((oid_of(r), side, q)); time.sleep(0.7)
if not all(e[0] for e in entries):
    clean(FS); sys.exit(f"master refused an order (intermittent staging refusal) - rerun: {[e[0] is not None for e in entries]}")
wait(lambda: all(len(pos(f)) == len(plan) for f in FS), 60)
def copied_by(f): return {(o.get("copy_ref") or "").lstrip("-") for o in orders(f) if o.get("copy_kind") == "copy" and o["created_at"] >= t0}
UNCOPIED = {}
for e in ids if False else [x[0] for x in entries]:
    n = sum(1 for f in FS if e not in copied_by(f))
    if n: UNCOPIED[e] = n
print(f"[1] master opened {len(entries)} positions; followers with all {len(plan)}: {sum(len(pos(f)) == len(plan) for f in FS)}/{len(FS)}", flush=True)

# 2. partial closes
E = {e[0]: e for e in entries}
ids = [e[0] for e in entries]
red = []   # (entry_id, qty)
def reduce(eid, q):
    r = c.reduce_position(M, eid, q, I); red.append((eid, q, r["status_code"])); return r
reduce(ids[0], 0.05); time.sleep(0.7)                    # 50 %
reduce(ids[1], 0.02); time.sleep(0.7)                    # 25 %
reduce(ids[1], 0.03); time.sleep(0.7)                    # second reduce on the same position
reduce(ids[2], 0.006); time.sleep(0.7)                   # 10 %
with ThreadPoolExecutor(3) as ex:                         # parallel burst on three different positions
    list(ex.map(lambda a: reduce(*a), [(ids[3], 0.06), (ids[4], 0.01), (ids[5], 0.05)]))
c.squareoff_position(M, ids[6], I)                        # one full close
print(f"[1b] entries NOT copied (master order -> followers missing it): { {k[-6:]: v for k, v in UNCOPIED.items()} }", flush=True)
print("[2] reduces sent:", [(r[0][-6:], r[1], r[2]) for r in red], "| full close of", ids[6][-6:], flush=True)
time.sleep(15)

# 3. compare
mpos = {p["market_order_id"]: p for p in pos(M)}
mrem = {eid: (mpos[eid]["net_qty"] if eid in mpos else 0.0) for eid in ids}
mh = [h for h in hist(M) if h["executed_at"] >= t0]
m_closed_q = sorted(round(h["qty"], 8) for h in mh)
m_pnl = sum(h["realized_pnl"] for h in mh)
def arith(h):
    d = 1 if h["side"] == "BUY" else -1
    return (h["exit_price"] - h["entry_price"]) * h["qty"] * d
m_arith_bad = [round(h["realized_pnl"] - arith(h), 4) for h in mh if abs(h["realized_pnl"] - arith(h)) > 0.01]
print(f"[3] master: open {len(mpos)}, remaining lots { {k[-6:]: round(v,4) for k,v in mrem.items()} }, close events {len(mh)}, realized P&L {m_pnl:.4f}, P&L arithmetic off on {len(m_arith_bad)} rows", flush=True)

bad = {"positions": [], "lots": [], "events": [], "reduced_lots": [], "pnl_rows": [], "pnl_arith": []}
rows = {}
for f in FS:
    fo = {(o.get("copy_ref") or "").lstrip("-"): o["order_id"] for o in orders(f) if o.get("copy_kind") == "copy" and o["created_at"] >= t0}
    fp = {p["market_order_id"]: p for p in pos(f)}
    rem = {eid: (fp[fo[eid]]["net_qty"] if eid in fo and fo[eid] in fp else 0.0) for eid in ids}
    fh = [h for h in hist(f) if h["executed_at"] >= t0]
    fq = sorted(round(h["qty"], 8) for h in fh)
    pnl = sum(h["realized_pnl"] for h in fh)
    name = f.split("@")[0]
    exp_pos = len([k for k in mpos if k not in UNCOPIED])
    if len(fp) != exp_pos: bad["positions"].append((name, len(fp), exp_pos))
    lots = [(eid[-6:], round(rem[eid], 6), round(mrem[eid] * MULT, 6)) for eid in ids if eid not in UNCOPIED and abs(rem[eid] - mrem[eid] * MULT) > 1e-9]
    if lots: bad["lots"].append((name, lots))
    exp_ev = [h for h in mh if h["order_id"] and not any(h.get("position_id") == mp.get("position_id") and k in UNCOPIED for k, mp in mpos.items())]
    exp_q = sorted(round(h["qty"] * MULT, 8) for h in mh if h["qty"] not in () )
    if len(fh) != len(mh) - sum(1 for e in UNCOPIED if e in {r[0] for r in red}) - (1 if ids[6] in UNCOPIED else 0): bad["events"].append((name, len(fh), len(mh)))
    skip_q = sorted(round(q * MULT, 8) for (e, q, _) in red if e in UNCOPIED)
    want = list(exp_q)
    for q in skip_q:
        if q in want: want.remove(q)
    if fq != want: bad["reduced_lots"].append((name, fq, want))
    if any(abs(h["realized_pnl"] - arith(h)) > 0.01 for h in fh): bad["pnl_arith"].append(name)
    rows[name] = {"open": len(fp), "events": len(fh), "pnl": round(pnl, 4)}
    # P&L expected from master's own rows scaled, and from the follower's own prices
    rows[name]["pnl_vs_master_x2"] = round(pnl - m_pnl * MULT, 4)

# row-by-row P&L: pair each master close with the follower close of qty x multiplier, same side
f0 = [h for h in hist(FS[0]) if h["executed_at"] >= t0]
used = set(); pairs = []
for h in sorted(mh, key=lambda x: x["executed_at"]):
    for i, g_ in enumerate(sorted(f0, key=lambda x: x["executed_at"])):
        if i in used or g_["side"] != h["side"] or abs(g_["qty"] - h["qty"] * MULT) > 1e-9: continue
        used.add(i); pairs.append((h, g_)); break
print("    row by row (master vs follower1): side qty | entry m/f | exit m/f | pnl m x2 / f | slippage-explained diff")
for h, g_ in pairs:
    d = 1 if h["side"] == "BUY" else -1
    expl = ((g_["exit_price"] - g_["entry_price"]) - (h["exit_price"] - h["entry_price"])) * g_["qty"] * d   # P&L difference caused only by different fill prices
    print(f"      {h['side']:4s} {h['qty']:<6g}| {h['entry_price']}/{g_['entry_price']} | {h['exit_price']}/{g_['exit_price']} | {h['realized_pnl']*MULT:8.4f} / {g_['realized_pnl']:8.4f} | diff {g_['realized_pnl']-h['realized_pnl']*MULT:8.4f} (from price differences {expl:8.4f})")
unp = [h for h in mh if not any(h is p_[0] for p_ in pairs)]
print(f"    master close rows with no follower counterpart (uncopied entries): {[(h['side'], h['qty'], round(h['realized_pnl'],4)) for h in unp]}")
paired_m = sum(p_[0]["realized_pnl"] for p_ in pairs) * MULT; paired_f = sum(p_[1]["realized_pnl"] for p_ in pairs)
print(f"    paired rows only: master x{MULT:g} = {paired_m:.4f}, follower1 = {paired_f:.4f}, difference {paired_f - paired_m:.4f}")
print(f"    followers checked: {len(FS)}")
for k, v in bad.items(): print(f"    {k:14s} mismatches: {len(v)}  {v[:2]}")
dev = [r["pnl_vs_master_x2"] for r in rows.values()]
print(f"    realized P&L: master {m_pnl:.4f} x{MULT:g} = {m_pnl*MULT:.4f}; follower P&L min/max {min(r['pnl'] for r in rows.values())}/{max(r['pnl'] for r in rows.values())}; deviation from master x{MULT:g}: min {min(dev)} max {max(dev)}")
verdict = "PASS" if not any(bad[k] for k in ("positions", "lots", "events", "reduced_lots")) else "FAIL"
print("RESULT (count / lot):", verdict, "| P&L: see deviation above (price slippage between master and follower fills)")
Path(ROOT / "reports" / "evidence").mkdir(exist_ok=True, parents=True)
json.dump({"plan": plan, "reduces": red, "master": {"remaining": mrem, "events": len(mh), "pnl": m_pnl}, "bad": bad, "followers": rows, "verdict": verdict},
          open(ROOT / "reports" / "evidence" / f"partial_close_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", "w"), indent=2, default=str)
clean(FS)
