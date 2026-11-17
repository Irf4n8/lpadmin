#!/usr/bin/env python3
"""Pending-order trigger edits (LIMIT / STOP, BUY / SELL): master + followers (staging, real / hedging, x2)."""
import sys, time, json
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import test_suite.go_live_spec_runner as g
from test_suite.go_live_spec_runner import *  # noqa

g.MID = c.get_copy_followers(M, I)[0]["master_client_id"]
FS = ALL if "--all" in sys.argv else ALL[:10]
for f in FS: follow(f)
RES = []
def rec(name, ok, detail):
    RES.append({"test": name, "ok": ok, "detail": detail}); print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)
def mod(e, oid, body): return c.oms(e, "PUT", f"/orders/{oid}/modify", I, json=body)
def row(e, oid): 
    r = [o for o in orders(e) if o.get("order_id") == oid]; return r[0] if r else None
def fol(oid_master):
    out = {}
    for f in FS:
        r = [o for o in orders(f) if (o.get("copy_ref") or "").lstrip("-") == oid_master and o.get("state") == "PENDING"]
        out[f.split("@")[0]] = (r[0].get("price"), r[0].get("trigger_price"), r[0].get("requested_qty")) if r else None
    return out
def summ(d): 
    vals = {}
    for v in d.values(): vals[v] = vals.get(v, 0) + 1
    return vals

clean(FS)
buy(); time.sleep(3); lp = pos(M)[0]["current_price"]; clean(FS); time.sleep(2)
print(f"live price ~{lp}")
cases = [("LIMIT", "BUY", lp - 400), ("LIMIT", "SELL", lp + 400), ("STOP", "BUY", lp + 400), ("STOP", "SELL", lp - 400)]

for kind, side, p0 in cases:
    p0 = round(p0, 1); tag = f"{kind} {side}"; fld = "price" if kind == "LIMIT" else "trigger_price"
    clean(FS)
    r = buy(order_type=kind, side=side, price=p0); oid = oid_of(r)
    if not oid: rec(tag, False, f"order refused {str(r['data'])[:100]}"); continue
    time.sleep(4)
    d0 = fol(oid)
    # A. three successive edits, each must reach master and every follower
    ok = True; seq = []
    for step, dp in enumerate((-50, -120, -30), 1):
        newp = round(p0 + (dp if kind == "LIMIT" and side == "BUY" or kind == "STOP" and side == "SELL" else -dp), 1)
        rr = mod(M, oid, {"price": newp}); time.sleep(4)
        m = row(M, oid); dd = fol(oid)
        mp = m.get(fld) if m else None
        got = summ({k: (v[0] if kind == "LIMIT" else v[1]) if v else None for k, v in dd.items()})
        good = rr["status_code"] == 200 and mp == newp and got == {newp: len(FS)}
        ok &= good; seq.append((newp, mp, good))
    rec(f"{tag}: 3 successive edits via {{price}}", ok, f"master/followers reached each new price: {[(a, b) for a, b, _ in seq]}; followers all at last price {summ({k: (v[0] if kind=='LIMIT' else v[1]) if v else None for k,v in fol(oid).items()})}")
    # B. other field names: which are honoured, which silently ignored
    base = row(M, oid).get(fld); eff = {}
    for i, key in enumerate(("price", "trigger_price", "new_price", "stop_price", "newPrice")):
        cur = row(M, oid).get(fld); tgt = round(cur - 11 - i, 1) if side == "BUY" and kind == "LIMIT" or kind == "STOP" and side == "SELL" else round(cur + 11 + i, 1)
        rr = mod(M, oid, {key: tgt}); time.sleep(2.5); m = row(M, oid)
        eff[key] = (rr["status_code"], "moved" if m.get(fld) == tgt else "IGNORED")
    rec(f"{tag}: field names", True, f"{eff}")
    # C. quantity edit
    q0 = row(M, oid)["requested_qty"]; newq = round(q0 * 2, 6)
    rr = mod(M, oid, {"price": row(M, oid).get(fld), "qty": newq}); time.sleep(4); m = row(M, oid)
    rr2 = mod(M, oid, {"price": row(M, oid).get(fld), "quantity": newq}); time.sleep(4); m2 = row(M, oid)
    fq = summ({k: v[2] if v else None for k, v in fol(oid).items()})
    rec(f"{tag}: quantity edit", m2["requested_qty"] == newq or m["requested_qty"] == newq,
        f"qty {q0} -> {m['requested_qty']} (field qty, HTTP {rr['status_code']}), -> {m2['requested_qty']} (field quantity, HTTP {rr2['status_code']}); follower qty {fq} (want {newq*MULT} if edited)")
    # D. edit to a price that crosses the market: should trigger / fill on master and followers
    cross = round(lp + 300, 1) if (kind == "LIMIT" and side == "BUY") or (kind == "STOP" and side == "SELL" and False) else None
    clean(FS)

# E. edit a pending order that carries TP/SL, then check protection survives
clean(FS)
r = buy(order_type="LIMIT", side="BUY", price=round(lp - 400, 1), tp=round(lp + 900, 1), sl=round(lp - 900, 1)); oid = oid_of(r); time.sleep(4)
if oid:
    m0 = row(M, oid); mod(M, oid, {"price": round(lp - 450, 1)}); time.sleep(4); m1 = row(M, oid)
    rec("pending LIMIT with TP/SL: edit price", m1.get("price") == round(lp - 450, 1), f"placed with tp/sl {(m0.get('tp'), m0.get('sl'))} -> after edit {(m1.get('tp'), m1.get('sl'))}; price {m0.get('price')} -> {m1.get('price')}; raw keys {sorted(m1)}")
else:
    rec("pending LIMIT with TP/SL", False, f"refused {str(r['data'])[:120]}")
clean(FS)

# F. edit a LIMIT so it becomes marketable: it must fill on master and be copied
r = buy(order_type="LIMIT", side="BUY", price=round(lp - 400, 1)); oid = oid_of(r); time.sleep(4)
rr = mod(M, oid, {"price": round(lp + 200, 1)}); time.sleep(8); m = row(M, oid)
rec("edit LIMIT BUY above market (marketable)", m and m["state"] == "FILLED" and all(netq(f) == 0.002 for f in FS),
    f"HTTP {rr['status_code']}, master state {m and m['state']}, followers holding 0.002: {sum(netq(f) == 0.002 for f in FS)}/{len(FS)}")
clean(FS)

# G. edit an order that is already filled / cancelled
r = buy(order_type="LIMIT", side="BUY", price=round(lp - 400, 1)); oid = oid_of(r); time.sleep(3)
c.cancel_order(M, oid, I); time.sleep(3)
rr = mod(M, oid, {"price": round(lp - 450, 1)})
rec("edit a CANCELLED order is refused", rr["status_code"] >= 400, f"HTTP {rr['status_code']} {str(rr['data'])[:90]}")
buy(); time.sleep(2); fid = orders(M)[0]["order_id"]
rr = mod(M, fid, {"price": 1.0}); rec("edit a FILLED order is refused", rr["status_code"] >= 400, f"HTTP {rr['status_code']} {str(rr['data'])[:90]}")
clean(FS)

# H. HFT bracket endpoint
r = c.oms(M, "POST", "/orders/bracket", I, json={"symbol": "BINANCE:BTCUSDT.P", "side": "BUY", "qty": 0.001}); print("  bracket/HFT endpoint:", r["status_code"], str(r["data"])[:120])
for pth in ("/orders/stop-hft", "/orders/hft"):
    r = c.oms(M, "POST", pth, I, json={}); print("  ", pth, r["status_code"], str(r["data"])[:80])
json.dump(RES, open(ROOT / "reports" / "evidence" / f"pending_edit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", "w"), indent=2, default=str)
print(f"\nSUMMARY: {sum(r['ok'] for r in RES)} pass / {sum(not r['ok'] for r in RES)} fail of {len(RES)}")
clean(FS)
