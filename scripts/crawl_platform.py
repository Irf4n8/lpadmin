"""Read-only crawl: log in with a browser, open the workspace and list every API call + JS bundle it loads.
Usage: python scripts/crawl_platform.py [email]   (default: the master).  Screenshot -> scratch/crawl/"""
import sys,json,re,time,os
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT)); os.makedirs(ROOT/'scratch'/'crawl',exist_ok=True); os.chdir(ROOT)
from playwright.sync_api import sync_playwright
from config.settings import BASE_URL, MEMBER_PASSWORD, MASTER_EMAIL
who=sys.argv[1] if len(sys.argv)>1 else MASTER_EMAIL
reqs={}; assets=set()
with sync_playwright() as p:
    b=p.chromium.launch(headless=True); ctx=b.new_context(viewport={'width':1600,'height':1000}); pg=ctx.new_page()
    def on_req(r):
        u=r.url
        if '/v1/oms' in u or '/api/' in u or 'copy' in u.lower():
            reqs[(r.method,re.sub(r'(ord|pos|mem|cfl|grp)_[0-9a-f]+','<id>',u.split('?')[0]))]=reqs.get((r.method,re.sub(r'(ord|pos|mem|cfl|grp)_[0-9a-f]+','<id>',u.split('?')[0])),0)+1
        if u.endswith('.js') or '.js?' in u: assets.add(u.split('?')[0])
    ctx.on('request',on_req)
    pg.goto(BASE_URL+'/login'); pg.fill('input[type=email],input[name=email]',who); pg.fill('input[type=password]',MEMBER_PASSWORD)
    pg.click('button[type=submit]'); pg.wait_for_timeout(4000)
    pg.goto(BASE_URL+'/dashboard'); pg.wait_for_timeout(12000)
    print('url',pg.url); print('frames',[f.url[:100] for f in pg.frames])
    pg.screenshot(path='scratch/crawl/dash_'+who.split('@')[0]+'.png')
    for f in pg.frames:
        try: print('FRAME TEXT',f.url[:60],'|',f.inner_text('body')[:600].replace('\n',' / '))
        except Exception as e: pass
    b.close()
print('\nREQUESTS'); [print(' ',m,u,n) for (m,u),n in sorted(reqs.items(),key=lambda x:x[0][1])]
print('\nJS assets'); [print(' ',a) for a in sorted(assets)]
