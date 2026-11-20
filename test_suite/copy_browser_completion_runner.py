"""Read-only Copy Trading browser checks. No MAM/PAMM actions or trade writes.
Run: .venv/bin/python test_suite/copy_browser_completion_runner.py --confirm-staging
"""
import argparse,json,sys,time
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from config.settings import BASE_URL,MEMBER_PASSWORD,ADMIN_EMAIL,ADMIN_PASSWORD
from playwright.sync_api import sync_playwright

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--confirm-staging',action='store_true');args=ap.parse_args()
 if not args.confirm_staging or BASE_URL!='https://lpadmin.blackfx.com':ap.error('Authorized staging only')
 accounts=json.loads((ROOT/'reports/netting_fresh_accounts.json').read_text())['accounts']
 email=next(a['email'] for a in accounts if a['intended_role']=='follower1')
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'reports/evidence'/('copy_browser_'+stamp);out.mkdir()
 rows=[];network=[]
 def save():
  report={'suite':'Copy Trading browser completion','timestamp':stamp,'host':BASE_URL,'cases':rows,'scope':'Read-only browser checks; no live trade or injected broker fault claims.'}
  (out/'execution.json').write_text(json.dumps(report,indent=2));(ROOT/'reports/copy_browser_latest.json').write_text(json.dumps(report,indent=2))
 def check(tid,description,steps,expected,fn,page=None):
  start=time.monotonic()
  try:
   ok,actual=fn();status='PASS' if ok else 'FAIL'
  except Exception as e:status='BLOCKED';actual='Automation could not complete this check: '+type(e).__name__+': '+str(e).splitlines()[0][:180]
  shot=out/(tid+'.png')
  if page:
   try:page.screenshot(path=str(shot),full_page=False)
   except Exception:pass
  rows.append(dict(tc_id=tid,description=description,preconditions='Dedicated staging follower account; Chromium browser. No orders are submitted.',steps=steps,test_data='Follower 1; desktop viewport 1440x900 unless specified.',expected=expected,actual=actual,status=status,severity='Medium' if status=='FAIL' else '—',defect_id='UI-'+tid if status=='FAIL' else '—',remarks='Read-only UI check; does not prove in-flight trade recovery.',script='test_suite/copy_browser_completion_runner.py',reproduce_command='.venv/bin/python test_suite/copy_browser_completion_runner.py --confirm-staging',evidence=[str(shot.relative_to(ROOT))] if shot.exists() else [],duration_s=round(time.monotonic()-start,2)))
  print(tid,status,actual,flush=True);save()
 def login(pg,user=email,pwd=MEMBER_PASSWORD):
  pg.goto(BASE_URL+'/login',wait_until='networkidle');pg.wait_for_timeout(600);pg.locator('input[type=email]').fill(user);pg.locator('input[type=password]').fill(pwd);pg.get_by_role('button',name='Log in',exact=True).click();pg.wait_for_timeout(2500)
 def logged(pg):return '/login' not in pg.url and pg.request.get(BASE_URL+'/api/auth/me').status==200
 def terminal(pg):
  pg.goto(BASE_URL+'/dashboard',wait_until='domcontentloaded')
  end=time.monotonic()+35
  while time.monotonic()<end:
   for f in pg.frames:
    try:
     if 'chartv2.' in f.url and f.locator('button[title="Add widget"]').count():
      if not f.get_by_text('Copy trading',exact=True).count():
       f.locator('button[title="Add widget"]').click()
      return f
    except Exception:pass
   pg.wait_for_timeout(500)
  raise RuntimeError('Terminal widget menu did not become available within 35 seconds')
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True);ctx=browser.new_context(viewport={'width':1440,'height':900});pg=ctx.new_page();pg.set_default_timeout(12000)
  pg.on('response',lambda r:network.append({'status':r.status,'path':r.url.split('?')[0]}) if r.status>=500 else None)
  def gate():
   pg.goto(BASE_URL+'/dashboard',wait_until='domcontentloaded');pg.wait_for_timeout(2000);return '/login' in pg.url,'Unauthenticated dashboard ended at '+pg.url.split('?')[0]
  check('CTUI-001','Block dashboard access before login','1. Open dashboard in a new browser context.\n2. Check redirect.','Redirect to login.',gate,pg)
  def masking():
   pg.goto(BASE_URL+'/login');p=pg.locator('input[type=password]');p.fill('MaskingCheck123');return p.get_attribute('type')=='password','Password input has type=password; characters are masked by the browser.'
  check('CTUI-002','Mask the password field','1. Open login.\n2. Enter a sample password.\n3. Inspect input type.','Password input remains masked.',masking,pg)
  def invalid():
   login(pg,'copy-browser-nobody@mailinator.com','wrong');txt=pg.locator('body').inner_text().lower();ok='/login' in pg.url and any(w in txt for w in ('invalid','incorrect','error','failed','wrong'));return ok,'Login rejected with a visible error.' if ok else 'Could not confirm both rejection and a visible error.'
  check('CTUI-003','Reject invalid login credentials','1. Submit an unregistered email and wrong password.\n2. Check error and current page.','Stay on login and display an error.',invalid,pg)
  def valid():login(pg);return logged(pg),'Valid follower login ended at '+pg.url.split('?')[0]
  check('CTUI-004','Log in with the dedicated follower','1. Enter valid follower credentials.\n2. Submit login.','Authenticated account page opens.',valid,pg)
  def refresh():
   if not logged(pg):raise RuntimeError('Valid login prerequisite was not established')
   pg.reload(wait_until='domcontentloaded');pg.wait_for_timeout(1500);return logged(pg),'Account remained authenticated after refresh.'
  check('CTUI-005','Keep login after account-page refresh','1. Log in.\n2. Refresh the account page.','Account stays authenticated.',refresh,pg)
  def copytab():
   f=terminal(pg);f.get_by_text('Copy trading',exact=True).first.click();pg.wait_for_timeout(2500);txt=f.locator('body').inner_text();(out/'copy_tab_text.txt').write_text(txt);return len(txt.strip())>80,'Copy Trading tab opened and rendered '+str(len(txt))+' characters of terminal content.'
  check('CTUI-006','Open the Copy Trading tab','1. Open dashboard.\n2. Click Copy trading.\n3. Check rendered content.','Copy Trading content renders.',copytab,pg)
  def refreshterm():
   f=terminal(pg);f.get_by_text('Copy trading',exact=True).first.click();pg.wait_for_timeout(1000);return len(f.locator('body').inner_text().strip())>80,'Terminal and Copy Trading tab rendered after dashboard navigation/reload. Active-trade reconciliation was not exercised.'
  check('CTUI-007','Reload the Copy Trading terminal','1. Reload dashboard.\n2. Reopen Copy trading.','Terminal renders again without losing the browser session.',refreshterm,pg)
  def tabs():
   other=ctx.new_page()
   try:
    other.goto(BASE_URL+'/account');other.wait_for_timeout(1200);return logged(other),'A second tab in the same context opened the authenticated account page.'
   finally:other.close()
  check('CTUI-008','Share the login with a second tab','1. Open account in another tab in the same browser context.','Second tab has the same authenticated session.',tabs,pg)
  def isolated():
   c=browser.new_context();p=c.new_page()
   try:p.goto(BASE_URL+'/account');p.wait_for_timeout(1200);return '/login' in p.url,'A separate browser context was redirected to login.'
   finally:c.close()
  check('CTUI-009','Keep a separate browser context signed out','1. Open account in a new isolated context.','Existing login is not inherited.',isolated,pg)
  def offline():
   ctx.set_offline(True)
   try:
    try:pg.reload(wait_until='domcontentloaded',timeout=8000)
    except Exception:pass
   finally:ctx.set_offline(False)
   terminal(pg);return logged(pg),'Dashboard loaded after the browser returned online. No in-flight trade or broker reconnect was tested.'
  check('CTUI-010','Recover dashboard loading after going offline','1. Set browser offline.\n2. Attempt reload.\n3. Restore network and reopen dashboard.','Dashboard loads after connection returns.',offline,pg)
  def slow():
   session=ctx.new_cdp_session(pg);session.send('Network.enable');session.send('Network.emulateNetworkConditions',{'offline':False,'latency':400,'downloadThroughput':150000,'uploadThroughput':75000})
   try:terminal(pg);return logged(pg),'Dashboard rendered with 400 ms emulated latency and 150 KB/s download. No trade delivery SLA is claimed.'
   finally:session.send('Network.emulateNetworkConditions',{'offline':False,'latency':0,'downloadThroughput':-1,'uploadThroughput':-1});session.detach()
  check('CTUI-011','Load dashboard on a slow browser connection','1. Emulate 400 ms latency.\n2. Open dashboard.\n3. Restore network.','Dashboard remains accessible under the emulated connection.',slow,pg)
  def mobile():
   pg.set_viewport_size({'width':390,'height':844});pg.goto(BASE_URL+'/account');pg.wait_for_timeout(1000);over=pg.evaluate('document.documentElement.scrollWidth > innerWidth + 2');return logged(pg) and not over,'Mobile account authenticated; horizontal overflow='+str(over)
  check('CTUI-012','Display the account page on a mobile viewport','1. Set viewport to 390x844.\n2. Open account.\n3. Check horizontal overflow.','Account renders without horizontal overflow.',mobile,pg)
  def logout():
   pg.get_by_text('Log out',exact=True).first.click();pg.wait_for_timeout(1000);pg.goto(BASE_URL+'/dashboard');pg.wait_for_timeout(1500);return '/login' in pg.url,'After logout, dashboard ended at '+pg.url.split('?')[0]
  check('CTUI-013','Block dashboard access after logout','1. Click Log out.\n2. Reopen dashboard.','Dashboard redirects to login.',logout,pg)
  def empty_login():
   pg.goto(BASE_URL+'/login',wait_until='networkidle');pg.wait_for_timeout(600);pg.get_by_role('button',name='Log in',exact=True).click();invalid=pg.locator('input:invalid').count();return '/login' in pg.url and invalid>0,'Empty login stayed on login; browser-invalid required fields: '+str(invalid)
  check('CTUI-014','Reject login with empty fields','1. Open login.\n2. Submit without email or password.','Required-field validation prevents login.',empty_login,pg)
  def forgot():
   pg.get_by_text('Forgot password?',exact=True).click();pg.wait_for_timeout(1000);txt=pg.locator('body').inner_text().lower();return 'reset' in txt or 'forgot' in txt,'Forgot-password link opened '+pg.url.split('?')[0]+'. No reset email was requested.'
  check('CTUI-015','Open the forgot-password page','1. Click Forgot password.\n2. Check destination content.','Password-reset page opens.',forgot,pg)
  def admin():
   pg.set_viewport_size({'width':1440,'height':900});pg.goto(BASE_URL+'/blackadmin',wait_until='networkidle');pg.wait_for_timeout(600)
   if pg.locator('input[type=email]').count():
    pg.locator('input[type=email]').fill(ADMIN_EMAIL);pg.locator('input[type=password]').fill(ADMIN_PASSWORD);pg.locator('input[type=password]').press('Enter');pg.wait_for_timeout(3000)
   txt=pg.locator('body').inner_text();return 'Members' in txt or 'People' in txt,'Admin page rendered; member-navigation presence='+str('Members' in txt or 'People' in txt)
  check('CTUI-016','Log in to the staging admin page','1. Open blackadmin.\n2. Enter configured admin credentials.\n3. Check member navigation.','Admin navigation renders.',admin,pg)
  def admin_members():
   loc=pg.get_by_text('Members',exact=True)
   if loc.count():loc.first.click()
   else:pg.get_by_text('People',exact=True).first.click()
   pg.wait_for_timeout(1500);txt=pg.locator('body').inner_text();return 'mailinator.com' in txt or 'Email' in txt,'Member list/table rendered. No member data was changed.'
  check('CTUI-017','Open the admin member list','1. Click Members or People.\n2. Check the member table.','Member list renders.',admin_members,pg)
  ctx.close();browser.close()
 (out/'http_5xx.json').write_text(json.dumps(network,indent=2));save();print('EVIDENCE',out)
if __name__=='__main__':main()
