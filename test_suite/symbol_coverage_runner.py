#!/usr/bin/env python3
"""
Symbol Coverage - copy trading on EVERY symbol the platform lists
=================================================================
The platform publishes its tradable universe at the `symbol_url` from GET /api/config
(currently https://terminal.blacktrader.com/feed/symbol_list, ~3 600 markets: Binance crypto perps/spot,
forex, metals, commodities, CFDs, US/EU stocks, spot indices, NSE/BSE stocks, futures, options, ...).

For every symbol the master opens a small market BUY, every linked follower must mirror it at
master qty x factor, then the master closes and every follower must be flat again. Symbols are
processed in BATCHES (default 20 at once) so one follower read verifies a whole batch.

Per-symbol verdict
    PASS    opened, copied to every linked follower at the right size, closed everywhere
    FAIL    copy missing / wrong size, follower not flat after the master closed, or a 5xx
    WARN    master order rejected for a reason other than "market closed", or a data-feed symbol accepted an order
    SKIP    market closed right now (re-run during that market's session)

Quantity: 2 x the symbol's lot size (so 0.5x followers still get a whole lot).

Usage
    python test_suite/symbol_coverage_runner.py --end 10                     # every symbol, followers 1-10
    python test_suite/symbol_coverage_runner.py --sample                     # one symbol per market type (~2 min)
    python test_suite/symbol_coverage_runner.py --types FOREX,METAL --end 5  # only some market types
    python test_suite/symbol_coverage_runner.py --symbols BLACK:XAUUSD,BINANCE:BTCUSDT.P
"""

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config.settings import BASE_URL, DEFAULT_PREFIX, DEFAULT_DOMAIN, MASTER_EMAIL, MASTER_ID, FOLLOWER_COUNT
from test_suite.breakpoint_race_runner import pos_qty
from test_suite.client import BlackTraderClient

DEFAULT_SYMBOL_URL = "https://terminal.blacktrader.com/feed/symbol_list"
DATA_FEED_TYPES = {"GREEKS"}           # analytics series (IV / OI / fair value) - not instruments
SYNC_TIMEOUT = 30.0


# --------------------------------------------------------------------------------------------- symbol universe
def symbol_url() -> str:
    try:
        u = requests.get(f"{BASE_URL}/api/config", timeout=15).json().get("symbol_url")
        return u or DEFAULT_SYMBOL_URL
    except Exception:
        return DEFAULT_SYMBOL_URL


_UNIVERSE: Optional[List[Dict[str, Any]]] = None


def load_symbols() -> List[Dict[str, Any]]:
    """Every market the platform publishes, as {sym, type, group, lot, step, max_qty, csize, ckind}.

    precisionMap[symbol] = [price_decimals, qty_step, [min_qty, max_qty, qty_step], contract]
    contract = 1 (PnL = price diff x qty)  or  [kind, _, contract_size, conversion_symbol]
        type1, and type3 whose conversion symbol is itself (EURUSD): PnL = diff x qty x contract_size, exact.
        type2 (USDJPY), type3 crosses (GBPJPY, EURGBP) and type4 crosses (CADCHF, CHFJPY): PnL is converted to the account currency at a live rate
        that the history row does not carry, so it cannot be recomputed. Observed on 2026-11-12: the engine uses
        100 000 units per lot for these pairs, not the listed size. They are checked for sign and for an identical
        PnL-per-unit on master and followers instead (see sweep()).
    """
    global _UNIVERSE
    if _UNIVERSE is not None:
        return _UNIVERSE
    data = requests.get(symbol_url(), timeout=60).json()["data"]
    pm = data.get("precisionMap", {})
    out = []
    for m in data["markets"]:
        p = pm.get(m["symbol"]) or []
        rng = p[2] if len(p) > 2 and isinstance(p[2], list) and len(p[2]) == 3 else [1, 0, 1]
        con = p[3] if len(p) > 3 else 1
        csize, ckind = (float(con[2] or 1), str(con[0])) if isinstance(con, list) and len(con) > 2 else (1.0, "unit")
        sym = f"{m['exchange']}:{m['symbol']}"
        conv = str(con[3]) if isinstance(con, list) and len(con) > 3 and con[3] else ""
        # type2 = USD-base pair (USDJPY), type3 = USD-quote pair or cross via XXXUSD, type4 = cross via USDXXX (CADCHF)
        converted = ckind in ("type2", "type4") or (ckind == "type3" and conv and conv != sym)
        group = m["type"] + (f"/{m['sub']}" if m.get("sub") else "")
        out.append({"sym": sym, "type": m["type"], "group": group, "converted": bool(converted),
                    "lot": float(m.get("lot") or 1), "step": float(rng[2] or rng[0] or 1), "min_qty": float(rng[0] or 0),
                    "max_qty": float(rng[1] or 0), "csize": csize, "ckind": ckind, "expiry": m.get("expiry")})
    _UNIVERSE = out
    return out


def symbol_meta() -> Dict[str, Dict[str, Any]]:
    return {s["sym"]: s for s in load_symbols()}


def expected_pnl(row: Dict[str, Any], meta: Optional[Dict[str, Any]]) -> Optional[float]:
    """Realized PnL a closed trade should carry, from the symbol's contract spec. None = needs a live FX rate."""
    if meta is not None and meta.get("converted"):
        return None
    return signed_move(row) * (meta["csize"] if meta else 1.0)


def signed_move(row: Dict[str, Any]) -> float:
    q, en, ex = float(row.get("qty") or 0), float(row.get("entry_price") or 0), float(row.get("exit_price") or 0)
    return (ex - en) * q * (1 if row.get("side") == "BUY" else -1)


def pnl_tolerance(meta: Optional[Dict[str, Any]], expected: float) -> float:
    return 0.01 + 1e-9 * abs(expected)


def converted_pnl_issues(rows: List[tuple]) -> List[str]:
    """rows: (account, history_row) for ONE currency-converted symbol. Checks sign and equal PnL per unit of move."""
    issues, ratios = [], []
    for acc, h in rows:
        move, got = signed_move(h), float(h.get("realized_pnl") or 0)
        if abs(move) < 1e-12:
            if abs(got) > 0.01:
                issues.append(f"{acc} realized {round(got, 6)} although entry == exit")
            continue
        if got and (got > 0) != (move > 0):
            issues.append(f"{acc} realized {round(got, 6)} has the opposite sign of its price move")
        ratios.append((acc, got / move))
    if len(ratios) > 1:
        lo, hi = min(r for _, r in ratios), max(r for _, r in ratios)
        if hi - lo > 0.01 * max(abs(lo), abs(hi)):
            issues.append("PnL per unit differs between accounts: " + ", ".join(f"{a} {r:.2f}" for a, r in ratios[:5]))
    return issues


def sample_per_group(symbols: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One symbol per market group (type/sub). Prefers well-known liquid names when present."""
    prefer = {"BINANCE:BTCUSDT.P", "BINANCE:BTCUSDT", "BINANCE:BTCUSD_PERP.P", "BLACK:EURUSD", "BLACK:XAUUSD", "BLACK:AAPL.OQ",
              "BLACK:US500cash-1", "BLACK:BTCUSD", "NSE:RELIANCE", "NSE:NIFTY", "BLACK:GOLD.247", "BLACK:BRENTcash-1"}
    best: Dict[str, Dict[str, Any]] = {}
    for s in symbols:
        g = s["group"]
        if g not in best or (s["sym"] in prefer and best[g]["sym"] not in prefer):
            best[g] = s
    return list(best.values())


def order_qty(s: Dict[str, Any]) -> float:
    """2 x max(step, min qty): a 0.5x follower still gets a valid size (>= min, a whole step), 3x stays far below max.

    Sizing below the minimum is NOT what this suite tests: observed 2026-11-12 on BLACK:US30cash-1 (min 1, step 0.1)
    a master order of 1 copied to 0.5x followers as 1.0 - sub-minimum copies are rounded UP to the minimum.
    """
    step = s.get("step") or s.get("lot") or 1.0
    q = 2 * max(step, s.get("min_qty") or 0)
    return float(f"{q:.10g}")


# --------------------------------------------------------------------------------------------- the sweep
def net_by_symbol(positions: List[dict]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for p in positions:
        sym = p.get("symbol")
        out[sym] = out.get(sym, 0.0) + (1 if p.get("side") == "BUY" else -1) * pos_qty(p)
    return out


def _tol(exp: float) -> float:
    return max(2e-3, 0.01 * abs(exp))


def _short(e: str) -> str:
    return e.split("@")[0]


def sweep(c: BlackTraderClient, master: str, linked: List[str], factor: Dict[str, float], inst: str,
          symbols: List[Dict[str, Any]], batch: int = 20, log: Callable[[str], None] = print,
          workers: int = 8) -> List[Dict[str, Any]]:
    """Open -> verify copies -> close -> verify flat -> verify realized PnL, `batch` symbols at a time.
    Returns one result per symbol."""
    results: List[Dict[str, Any]] = []
    meta = {s["sym"]: s for s in symbols}
    # accounting is checked on the master + one follower per distinct copy factor (history reads are costly)
    seen_f, auditors = set(), [master]
    for e in linked:
        k = round(factor[e], 6)
        if k not in seen_f and len(auditors) < 5:
            seen_f.add(k); auditors.append(e)

    def hist(e):
        return c.get_history(e, inst).get("history", []) or []
    with ThreadPoolExecutor(max_workers=5) as ex:
        mark = {e: max([int(h.get("history_id") or 0) for h in rows] or [0]) for e, rows in zip(auditors, ex.map(hist, auditors))}

    for b0 in range(0, len(symbols), batch):
        chunk = symbols[b0:b0 + batch]
        t0 = time.time()

        def place(s):
            r = c.place_order(master, symbol=s["sym"], side="BUY", qty=order_qty(s), instance=inst)
            return s, r
        with ThreadPoolExecutor(max_workers=workers) as ex:
            placed = list(ex.map(place, chunk))

        opened: Dict[str, Dict[str, Any]] = {}
        for s, r in placed:
            res = {"symbol": s["sym"], "type": s["type"], "group": s["group"], "qty": order_qty(s), "status": None, "detail": ""}
            code, data = r["status_code"], r["data"]
            if code == 200 and isinstance(data, dict):
                pos = data.get("position") or {}
                res["entry"] = pos.get("avg_entry_price")
                opened[s["sym"]] = res
                if s["type"] in DATA_FEED_TYPES:
                    res["note"] = "data-feed symbol accepted an order"
            elif code >= 500:
                res.update(status="FAIL", detail=f"master order -> HTTP {code}: {str(data)[:160]}")
            elif "market closed" in str(data).lower():
                res.update(status="SKIP", detail="market closed")
            else:
                msg = data.get("error") if isinstance(data, dict) else str(data)
                res.update(status="WARN", detail=f"master order rejected: HTTP {code} {str(msg)[:160]}")
            results.append(res)

        if opened and linked:
            # 1) every follower mirrors every opened symbol
            bad: Dict[str, List[str]] = {}
            deadline = time.time() + SYNC_TIMEOUT
            while True:
                mnet = net_by_symbol(c.get_positions(master, inst).get("positions", []))
                fdata = c.fetch_all_followers_positions(linked, instance=inst)
                bad = {}
                for e in linked:
                    fnet = net_by_symbol((fdata.get(e) or {}).get("positions", []) or [])
                    for sym in opened:
                        exp, got = mnet.get(sym, 0.0) * factor[e], fnet.get(sym, 0.0)
                        if abs(got - exp) > _tol(exp):
                            bad.setdefault(sym, []).append(f"{_short(e)} expected {round(exp, 6)} got {round(got, 6)}")
                if not bad or time.time() > deadline:
                    break
                time.sleep(1.0)
            for sym, res in opened.items():
                if sym in bad:
                    res.update(status="FAIL", detail=f"{len(bad[sym])}/{len(linked)} followers did not copy correctly: " + "; ".join(bad[sym][:3]))

        # 2) master closes -> everyone flat on these symbols
        c.bulk_squareoff(master, instance=inst)
        if opened and linked:
            leftover: Dict[str, List[str]] = {}
            deadline = time.time() + SYNC_TIMEOUT
            while True:
                fdata = c.fetch_all_followers_positions(linked, instance=inst)
                leftover = {}
                for e in linked:
                    for sym, q in net_by_symbol((fdata.get(e) or {}).get("positions", []) or []).items():
                        if sym in opened and abs(q) > 1e-9:
                            leftover.setdefault(sym, []).append(e)
                if not leftover or time.time() > deadline:
                    break
                time.sleep(1.0)
            for sym, who in leftover.items():
                r = opened[sym]
                msg = f"still open on {len(who)} follower(s) after the master closed: {', '.join(_short(e) for e in who[:5])}"
                r.update(status="FAIL", detail=(r["detail"] + " | " if r["detail"] else "") + msg)
            if leftover:            # recover so the next batch starts clean
                c.teardown_all_accounts(master, sorted({e for who in leftover.values() for e in who}), instance=inst)
        # 3) realized PnL of every closed trade matches the contract spec
        if opened:
            time.sleep(0.8)
            with ThreadPoolExecutor(max_workers=5) as ex:
                rows_by = dict(zip(auditors, ex.map(hist, auditors)))
            closed_on_master = set()
            converted_rows: Dict[str, List[tuple]] = {}

            def flag(sym, msg):
                res = opened[sym]
                res["status"] = "FAIL"
                res["detail"] = (res["detail"] + " | " if res["detail"] else "") + msg
            for e, rows in rows_by.items():
                new = [h for h in rows if int(h.get("history_id") or 0) > mark[e]]
                mark[e] = max([mark[e]] + [int(h.get("history_id") or 0) for h in new])
                for h in new:
                    sym = h.get("symbol")
                    if sym not in opened:
                        continue
                    if e == master:
                        closed_on_master.add(sym)
                    want = expected_pnl(h, meta.get(sym))
                    got = float(h.get("realized_pnl") or 0)
                    if want is None:
                        converted_rows.setdefault(sym, []).append((_short(e), h))
                    elif abs(got - want) > pnl_tolerance(meta.get(sym), want):
                        flag(sym, f"{_short(e)} realized PnL {round(got, 6)} but {h.get('side')} {h.get('qty')} "
                                  f"{h.get('entry_price')}->{h.get('exit_price')} x contract {meta[sym]['csize']:g} = {round(want, 6)}")
            for sym, rows in converted_rows.items():
                for msg in converted_pnl_issues(rows):
                    flag(sym, msg)
            for sym, res in opened.items():
                if sym not in closed_on_master and res["status"] is None:
                    res.update(status="WARN", detail="no closed trade for this symbol in the master's history")
        for sym, res in opened.items():
            if res["status"] is None:
                res["status"] = "WARN" if res.get("note") else "PASS"
                res["detail"] = res.get("note", "") or f"copied to {len(linked)} followers and closed"

        done = results[-len(chunk):]
        tally = {k: sum(r["status"] == k for r in done) for k in ("PASS", "FAIL", "WARN", "SKIP")}
        for r in done:
            if r["status"] != "SKIP":
                log(f"[{r['status']}] {r['symbol']:<38} {r['group']:<26} {r['detail']}")
        log(f"    batch {b0 // batch + 1}/{(len(symbols) + batch - 1) // batch}: {tally} ({time.time() - t0:.1f}s, "
            f"{min(b0 + batch, len(symbols))}/{len(symbols)} symbols)")
    return results


def summarize(results: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    by: Dict[str, Dict[str, int]] = {}
    for r in results:
        g = by.setdefault(r["group"], {"PASS": 0, "FAIL": 0, "WARN": 0, "SKIP": 0})
        g[r["status"]] += 1
    return dict(sorted(by.items()))


# --------------------------------------------------------------------------------------------- standalone
def linked_followers(c: BlackTraderClient, master: str, master_id: str, emails: List[str], inst: str):
    links = {l.get("follower_name"): l for l in c.get_copy_followers(master, instance=inst, active_only=True)
             if l.get("master_client_id") in (None, master_id)}
    fdata = c.fetch_all_followers_positions([master] + emails, instance=inst)
    fb = lambda e, k: float(((fdata.get(e) or {}).get("funds") or {}).get(k) or 0.0)
    factor, linked = {}, []
    for e in emails:
        l = links.get(_short(e))
        if not l:
            continue
        mult, method = float(l.get("multiplier") or 1.0), (l.get("method") or "multiplier").lower()
        f = mult * (fb(e, "balance") / (fb(master, "balance") or 1) if method == "balance"
                    else fb(e, "equity") / (fb(master, "equity") or 1) if method == "equity" else 1.0)
        factor[e] = -f if l.get("reverse") else f
        linked.append(e)
    return linked, factor


def write_reports(results, args, linked, started, universe_size) -> Path:
    ts = started.strftime("%Y%m%d_%H%M%S")
    out = BASE_DIR / "reports" / "evidence"
    out.mkdir(parents=True, exist_ok=True)
    groups = summarize(results)
    tally = {k: sum(g[k] for g in groups.values()) for k in ("PASS", "FAIL", "WARN", "SKIP")}
    verdict = "FAIL" if tally["FAIL"] else ("WARN" if tally["WARN"] else "PASS")
    meta = {"suite": "Symbol Coverage", "verdict": verdict, "timestamp": datetime.now(timezone.utc).isoformat(),
            "started": started.isoformat(timespec="seconds"), "duration_sec": round((datetime.now() - started).total_seconds(), 1),
            "instance": args.instance, "symbol_source": symbol_url(), "universe": universe_size, "tested": len(results),
            "mode": "sample" if args.sample else "all", "followers_range": [args.start, args.end], "followers_linked": len(linked),
            "tally": tally, "groups": groups, "results": results}
    jp, mp = out / f"symbols_evidence_{ts}.json", out / f"symbols_evidence_{ts}.md"
    jp.write_text(json.dumps(meta, indent=1, default=str), encoding="utf-8")
    lines = [f"# Symbol Coverage - {verdict}", "",
             f"**Run:** {meta['started']} ({meta['duration_sec']}s) | **Instance:** `{args.instance}` | "
             f"**Symbols tested:** {len(results)} of {universe_size} | **Followers:** {args.start}-{args.end} ({len(linked)} linked)", "",
             f"**Totals:** {tally['PASS']} pass, {tally['FAIL']} fail, {tally['WARN']} warn, {tally['SKIP']} skipped (market closed)", "",
             "| Market group | Pass | Fail | Warn | Closed |", "| :--- | ---: | ---: | ---: | ---: |"]
    lines += [f"| {g} | {v['PASS']} | {v['FAIL']} | {v['WARN']} | {v['SKIP']} |" for g, v in groups.items()]
    probs = [r for r in results if r["status"] in ("FAIL", "WARN")]
    lines += ["", "## Problems", ""] + ([f"- **{r['status']}** `{r['symbol']}` ({r['group']}): {r['detail']}" for r in probs[:300]] or ["- none"])
    lines += ["", "Closed markets are SKIPPED, not failed: re-run during that market's session "
                  "(Indian NSE/BSE 03:45-10:00 UTC, US stocks ~14:30-21:00 UTC, EU stocks 07:00-15:30 UTC)."]
    mp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return mp


def main() -> int:
    ap = argparse.ArgumentParser(description="Copy trading on every symbol the platform lists")
    ap.add_argument("--master", default=MASTER_EMAIL)
    ap.add_argument("--master-id", default=MASTER_ID)
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int, default=FOLLOWER_COUNT)
    ap.add_argument("--instance", default="paper", choices=["paper", "real"])
    ap.add_argument("--sample", action="store_true", help="one symbol per market group instead of every symbol")
    ap.add_argument("--types", default="", help="comma list of market types, e.g. FOREX,METAL,CRYPTO")
    ap.add_argument("--symbols", default="", help="comma list of exact symbols, e.g. BLACK:XAUUSD")
    ap.add_argument("--skip-data-feeds", action="store_true", help="leave out analytics series (GREEKS)")
    ap.add_argument("--batch", type=int, default=20)
    ap.add_argument("--i-understand-real-money", action="store_true")
    a = ap.parse_args()
    if a.instance != "paper" and not a.i_understand_real_money:
        print("Refusing to run on the REAL instance without --i-understand-real-money"); return 2
    if a.end < a.start:
        a.start, a.end = a.end, a.start
    started = datetime.now()
    universe = load_symbols()
    syms = universe
    if a.types:
        want = {t.strip().upper() for t in a.types.split(",") if t.strip()}
        syms = [s for s in syms if s["type"] in want]
    if a.symbols:
        want = {t.strip() for t in a.symbols.split(",") if t.strip()}
        syms = [s for s in syms if s["sym"] in want]
    if a.skip_data_feeds:
        syms = [s for s in syms if s["type"] not in DATA_FEED_TYPES]
    if a.sample:
        syms = sample_per_group(syms)
    print("=" * 90)
    print(f" SYMBOL COVERAGE | {a.instance.upper()} | {len(syms)} of {len(universe)} symbols | followers {a.start}-{a.end} | batch {a.batch}")
    print("=" * 90)
    if not syms:
        print("[FAIL] no symbols selected"); return 1
    c = BlackTraderClient(base_url=BASE_URL, max_workers=10)
    emails = [f"{DEFAULT_PREFIX}{i}@{DEFAULT_DOMAIN}" for i in range(a.start, a.end + 1)]
    linked, factor = linked_followers(c, a.master, a.master_id, emails, a.instance)
    print(f"[*] {len(linked)}/{len(emails)} followers linked to the master")
    c.teardown_all_accounts(a.master, emails, instance=a.instance)
    results: List[Dict[str, Any]] = []
    try:
        results = sweep(c, a.master, linked, factor, a.instance, syms, batch=max(1, min(a.batch, 50)))
    finally:
        c.teardown_all_accounts(a.master, emails, instance=a.instance)
        mp = write_reports(results, a, linked, started, len(universe))
    groups = summarize(results)
    print("\n" + "=" * 90)
    print(f" {'MARKET GROUP':<30} PASS  FAIL  WARN  CLOSED")
    for g, v in groups.items():
        print(f" {g:<30} {v['PASS']:>4}  {v['FAIL']:>4}  {v['WARN']:>4}  {v['SKIP']:>6}")
    print(f"\n Report: {mp}\n" + "=" * 90)
    return 1 if any(r["status"] == "FAIL" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
