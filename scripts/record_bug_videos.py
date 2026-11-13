#!/usr/bin/env python3
"""
Record screen videos (.webm) of each bug being reproduced LIVE against the platform.

    python scripts/record_bug_videos.py            # BUG-1, BUG-2, BUG-3 (terminal) + BUG-3 in the real trading terminal
    python scripts/record_bug_videos.py --only 2

Output: reports/videos/*.webm   (play in Chrome / Edge / VLC)
How:    a headless browser records a terminal-style window while scripts/repro_bugs.py runs for real and streams its
        output line by line; the BUG-3 UI video records the real web trading terminal logged in as the test account.
Safe:   paper instance, test account follower1, 0.01 BTC, positions are closed afterwards.
"""
import argparse
import html
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from config.settings import BASE_URL, MEMBER_PASSWORD, DEFAULT_PREFIX, DEFAULT_DOMAIN  # noqa: E402

OUT = ROOT / "reports" / "videos"
TMP = ROOT / "scratch" / "video_tmp"
EMAIL = f"{DEFAULT_PREFIX}1@{DEFAULT_DOMAIN}"

BUGS = {
    "2": ("BUG-2_wrong-order-type-returns-500", "BUG-2  Wrong order type returns HTTP 500 (should be 400)"),
    "3": ("BUG-3_invalid-TP-SL-silently-dropped", "BUG-3  Invalid TP/SL accepted (200) and silently dropped"),
    "1": ("BUG-1_orders-history-no-paging", "BUG-1  Orders history has no paging (whole history returned)"),
}

PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
body{margin:0;background:#0b0f17;color:#d7dde8;font-family:Consolas,'Cascadia Mono',monospace;font-size:19px}
.bar{background:#161d2b;padding:14px 22px;border-bottom:1px solid #2a3550;display:flex;gap:14px;align-items:center}
.dot{width:13px;height:13px;border-radius:50%%;display:inline-block}
.title{font:600 22px Segoe UI,Arial;color:#fff;margin-left:8px}
.sub{padding:8px 22px;background:#101624;color:#8fa0c0;font:15px Segoe UI,Arial;border-bottom:1px solid #2a3550}
#t{padding:18px 22px;white-space:pre-wrap;line-height:1.55}
.cmd{color:#7ee787}.hd{color:#5ac8fa;font-weight:700}.send{color:#ffd166}.ans{color:#fff}.ctl{color:#8b97b3}
.bad{color:#ff6b6b;font-weight:700}.good{color:#5be49b;font-weight:700}.cur{display:inline-block;width:11px;height:21px;background:#d7dde8;vertical-align:text-bottom}
</style></head><body>
<div class="bar"><span class="dot" style="background:#ff5f56"></span><span class="dot" style="background:#ffbd2e"></span><span class="dot" style="background:#27c93f"></span><span class="title">%(title)s</span></div>
<div class="sub">Live run against https://lpadmin.blackfx.com - paper instance - test account %(email)s</div>
<div id="t"></div></body></html>"""


def classify(line: str) -> str:
    if line.startswith("==="):
        return "hd"
    if line.startswith("SEND"):
        return "send"
    if "BUG REPRODUCED" in line:
        return "bad"
    if "OK (fixed)" in line or line.startswith("RESULT"):
        return "good" if "OK (fixed)" in line else "ans"
    if line.startswith("CONTROL") or line.startswith("NOTE"):
        return "ctl"
    return "ans"


def record_terminal(pw, key: str, pause: float):
    name, title = BUGS[key]
    TMP.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    for f in TMP.glob("*.webm"):
        f.unlink()
    browser = pw.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1280, "height": 720}, record_video_dir=str(TMP), record_video_size={"width": 1280, "height": 720})
    pg = ctx.new_page()
    pg.set_content(PAGE % {"title": html.escape(title), "email": EMAIL})
    pg.wait_for_timeout(1500)

    def add(text, cls):
        pg.evaluate("([t,c])=>{const s=document.createElement('span');s.className=c;s.textContent=t+'\\n';document.getElementById('t').appendChild(s);window.scrollTo(0,document.body.scrollHeight)}", [text, cls])

    cmd = f"$ python scripts/repro_bugs.py --only {key}"
    pg.evaluate("()=>{const s=document.createElement('span');s.id='cmd';s.className='cmd';document.getElementById('t').appendChild(s)}")
    for ch in cmd:                                   # typed command, like a real terminal
        pg.evaluate("c=>{document.getElementById('cmd').textContent+=c}", ch)
        pg.wait_for_timeout(35)
    pg.evaluate("()=>{document.getElementById('cmd').textContent+='\\n'}")
    pg.wait_for_timeout(600)

    proc = subprocess.Popen([sys.executable, "-u", str(ROOT / "scripts" / "repro_bugs.py"), "--only", key, "--pause", str(pause)],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", cwd=str(ROOT))
    for line in proc.stdout:
        line = line.rstrip("\n")
        add(line, classify(line))
        pg.wait_for_timeout(250)
    proc.wait()
    pg.wait_for_timeout(5000)
    ctx.close()
    browser.close()
    vid = next(TMP.glob("*.webm"))
    dest = OUT / f"{name}.webm"
    shutil.move(str(vid), dest)
    return dest, proc.returncode


def record_ui_bug3(pw):
    """The real web trading terminal: place the order through the API, show the position row with SL/TP empty."""
    name = "BUG-3_in-the-real-trading-terminal"
    TMP.mkdir(parents=True, exist_ok=True)
    for f in TMP.glob("*.webm"):
        f.unlink()
    s = requests.Session()
    s.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": MEMBER_PASSWORD}, timeout=30)
    token = s.post(f"{BASE_URL}/api/auth/chart-token", timeout=30).json()["token"]
    H = {"Authorization": "Bearer " + token, "X-Broker-ID": "paper", "Content-Type": "application/json"}
    oms = f"{BASE_URL}/v1/oms/paper"

    browser = pw.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1600, "height": 900}, record_video_dir=str(TMP), record_video_size={"width": 1600, "height": 900})
    pg = ctx.new_page()

    def banner(text, color="#1f6feb"):
        pg.evaluate("""([t,c])=>{let b=document.getElementById('bugbanner');
          if(!b){b=document.createElement('div');b.id='bugbanner';b.style.cssText='position:fixed;top:0;left:0;right:0;z-index:99999;padding:14px 22px;font:600 21px Segoe UI,Arial;color:#fff;box-shadow:0 4px 18px #0008';document.body.appendChild(b)}
          b.style.background=c;b.textContent=t}""", [text, color])

    try:
        pg.goto(f"{BASE_URL}/login")
        pg.wait_for_timeout(1500)
        pg.fill("input[type=email],input[name=email]", EMAIL)
        pg.fill("input[type=password]", MEMBER_PASSWORD)
        pg.wait_for_timeout(800)
        pg.click("button[type=submit]")
        pg.wait_for_timeout(2500)
        pg.goto(f"{BASE_URL}/dashboard")
        pg.wait_for_timeout(9000)
        banner("BUG-3 - real trading terminal, test account, Paper (Hedging). No open positions yet.")
        pg.wait_for_timeout(3000)
        banner("Sending a BUY 0.01 BTC with tp = -1 and sl = 1e30 (impossible TP/SL) ...", "#9a6700")
        pg.wait_for_timeout(2500)
        r = requests.post(f"{oms}/orders", headers=H, json={"symbol": "BINANCE:BTCUSDT.P", "side": "BUY", "type": "MARKET", "qty": 0.01, "tp": -1, "sl": 1e30}, timeout=60)
        banner(f"Platform answered HTTP {r.status_code} - the order was ACCEPTED and filled (expected: rejected with 400)", "#b62324")
        pg.wait_for_timeout(5000)
        for fr in pg.frames:                           # refresh the Trades panel if the push has not arrived yet
            try:
                fr.locator("button[title*='efresh'],button[aria-label*='efresh']").first.click(timeout=1500)
            except Exception:
                pass
        pg.wait_for_timeout(5000)
        banner("Look at the Positions table: the new position has NO SL and NO TP ('-'). The impossible values were silently thrown away - the trade is unprotected.", "#b62324")
        pg.wait_for_timeout(9000)
        pg.screenshot(path=str(OUT / "BUG-3_in-the-real-trading-terminal.png"))
    finally:
        for p in requests.get(f"{oms}/positions", headers=H, timeout=30).json().get("positions", []):
            requests.post(f"{oms}/positions/{p['market_order_id']}/squareoff", headers=H, json={}, timeout=30)
        ctx.close()
        browser.close()
    vid = next(TMP.glob("*.webm"))
    dest = OUT / f"{name}.webm"
    shutil.move(str(vid), dest)
    return dest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="2,3,1,ui")
    ap.add_argument("--pause", type=float, default=1.3)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    made = []
    with sync_playwright() as pw:
        for key in [x.strip() for x in a.only.split(",")]:
            if key in BUGS:
                print(f"[*] recording {BUGS[key][1]} ...", flush=True)
                made.append(record_terminal(pw, key, a.pause)[0])
            elif key == "ui":
                print("[*] recording BUG-3 in the real trading terminal ...", flush=True)
                made.append(record_ui_bug3(pw))
    print("\nVideos:")
    for m in made:
        print(f"  {m}  ({m.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
