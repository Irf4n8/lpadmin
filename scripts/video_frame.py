"""Grab a still frame from a .webm (no ffmpeg needed): python scripts/video_frame.py <video.webm> <seconds|end> <out.png>"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
v, t, out = Path(sys.argv[1]).resolve(), sys.argv[2], sys.argv[3]
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1280, "height": 720})
    pg.goto(v.as_uri()); pg.wait_for_selector("video"); pg.wait_for_timeout(500)
    # webm from the recorder has no duration metadata: force it by seeking far, then read the real end
    pg.evaluate("v=>{v.currentTime=1e9}", pg.query_selector("video")); pg.wait_for_timeout(800)
    dur = pg.evaluate("v=>v.currentTime", pg.query_selector("video"))
    target = dur - 0.3 if t == "end" else float(t)
    pg.evaluate("([v,t])=>{v.pause();v.currentTime=t}", [pg.query_selector("video"), target]); pg.wait_for_timeout(900)
    pg.screenshot(path=out); print(f"duration ~{dur:.1f}s, frame at {target:.1f}s -> {out}")
    b.close()
