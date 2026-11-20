"""Isolated 100-follower Copy Trading staging exercise. Retains fresh accounts; clears trades, links and balances."""
import argparse,json,sys,time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import requests
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from config import settings as cfg
from test_suite.client import BlackTraderClient

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--confirm-staging',action='store_true');a=ap.parse_args()
 if not a.confirm_staging or cfg.BASE_URL!='https://lpadmin.blackfx.com':ap.error('Authorized staging only')
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ').lower();out=ROOT/'reports/evidence'/('copy_scale_'+stamp);out.mkdir();c=BlackTraderClient(timeout=20,max_workers=12)
 raw=c.request_with_retry
 def once(method,url,**kw):kw['max_attempts']=1;return raw(method,url,**kw)
 c.request_with_retry=once
 admin=c.get_admin_token();manifest=[];rows=[];ready=[];mid=None;master=None;clean=False
 def each(fn,items,workers=12):
  with ThreadPoolExecutor(max_workers=workers) as ex:return list(ex.map(fn,items))
 def save():
  report=dict(suite='Isolated Copy Trading 100-follower scale',host=cfg.BASE_URL,timestamp=stamp,cases=rows,cleanup_verified=clean,evidence_directory=str(out))
  (out/'execution.json').write_text(json.dumps(report,indent=2));(ROOT/'reports/copy_scale_latest.json').write_text(json.dumps(report,indent=2));(out/'accounts.json').write_text(json.dumps(manifest,indent=2))
 def result(tid,title,ok,actual,expected,steps):
  rows.append(dict(tc_id=tid,description=title,preconditions='One fresh master and 100 fresh followers; B-book Real Hedging; funded with 100,000 staging units.',steps=steps,test_data='BLACK:EURUSD; BUY 0.01 lot; multiplier 1x; 100 followers.',expected=expected,actual=actual,status='PASS' if ok else 'FAIL',severity='High' if not ok else '—',defect_id='SCALE-'+tid if not ok else '—',remarks='Observed API behavior only. Worker-node distribution, database locks and queue internals are not independently visible.',script='test_suite/copy_scale_completion_runner.py',reproduce_command='.venv/bin/python test_suite/copy_scale_completion_runner.py --confirm-staging',evidence=[str((out/'details.json').relative_to(ROOT))]));save();print(tid,rows[-1]['status'],actual,flush=True)
 details={}
 def create(i):
  email=f'ctscale.{stamp}.{i:03d}@mailinator.com';r=requests.post(cfg.BASE_URL+'/admin/api/members',headers={'Authorization':'Bearer '+admin},json={'email':email,'password':cfg.MEMBER_PASSWORD,'name':'Copy Scale QA'},timeout=20)
  if r.status_code not in (200,201):raise RuntimeError('Fresh account create HTTP '+str(r.status_code)+': '+str(r.json().get('error','')))
  m=r.json()['member'];return {'email':email,'member_id':m['member_id']}
 try:
  # Save every completed creation even if a later creation fails.
  for offset in range(0,101,12):
   manifest.extend(each(create,list(range(offset,min(offset+12,101))),workers=6));save();print('Provisioned',len(manifest),'/101 fresh accounts',flush=True)
  master=manifest[0]['email'];mid=manifest[0]['member_id'];followers=[m['email'] for m in manifest[1:]]
  members={m['email'].lower():m for m in c.get_admin_members()}
  for m in manifest:
   if members[m['email']].get('book')!='b':raise RuntimeError('Fresh account is not B-book')
  def fund(m):
   state=c.get_positions(m['email'],'real')
   if 'error' in state or state['count'] or state['funds']['balance']!=0:raise RuntimeError('Fresh account is not initially flat and zero-funded')
   r=c.set_member_balance(m['member_id'],100000,'real')
   if r['status_code']!=200:raise RuntimeError('Fresh funding failed')
   return m['email']
  ready=each(fund,manifest)
  role=c.oms(master,'POST','/copy/master','real',json={'kind':'copy_manager','display_name':'Copy Scale QA Master'})
  if role['status_code']!=200:raise RuntimeError('Master role rejected')
  started=time.monotonic();first=each(lambda e:c.follow_master(e,mid,'real'),followers[:50],workers=50);elapsed=time.monotonic()-started
  links=c.get_copy_followers(master,'real');firstids={m['member_id'] for m in manifest[1:51]};linked={x['follower_client_id'] for x in links}
  details['subscribe50']=dict(statuses=[r['status_code'] for r in first],elapsed_s=elapsed,active_links=len(links))
  result('CTS-027','Subscribe 50 distinct followers concurrently',all(r['status_code']==200 for r in first) and linked==firstids,f'50 follow requests completed in {elapsed:.3f} seconds. Active unique links: {len(linked)}.','All fifty followers are linked exactly once.','1. Start with no follower links.\n2. Send fifty follow requests concurrently.\n3. Read master follower links and compare all fifty identities.')
  rest=each(lambda e:c.follow_master(e,mid,'real'),followers[50:]);links=c.get_copy_followers(master,'real')
  if len(links)!=100 or not all(r['status_code']==200 for r in rest):raise RuntimeError('100-follower topology not established')
  rr=c.place_order(master,symbol='BLACK:EURUSD',qty=.01,instance='real');oid=rr.get('data',{}).get('order',{}).get('order_id')
  if not oid:raise RuntimeError('Master order rejected')
  states={}
  for attempt in range(10):
   states=dict(zip(followers,each(lambda e:c.get_positions(e,'real'),followers)))
   if all('error' not in s and s.get('count')==1 for s in states.values()):break
   time.sleep(.5)
  good=all('error' not in s and s.get('count')==1 and s['positions'][0]['side']=='BUY' and abs(s['positions'][0]['net_qty']-.01)<1e-8 for s in states.values())
  correct=sum('error' not in s and s.get('count')==1 and abs(s['positions'][0]['net_qty']-.01)<1e-8 for s in states.values())
  details['fanout100']=dict(master_order_id=oid,positions=states)
  result('CTS-024','Copy one master BUY to 100 followers',good,f'{correct}/100 followers received one BUY position of 0.01 lot.','Each of 100 followers receives one correctly sized BUY copy.','1. Link all 100 followers.\n2. Submit master EURUSD BUY 0.01.\n3. Poll positions on every follower.\n4. Verify side, count and quantity.')
  close=c.bulk_squareoff(master,'real');time.sleep(1)
  flat=each(lambda e:c.get_positions(e,'real'),[master]+followers)
  allflat=all('error' not in s and s.get('count')==0 for s in flat)
  result('CTS-CLOSE','Close the master and all 100 copied positions',allflat,f'{sum("error" not in s and s.get("count")==0 for s in flat)}/101 accounts have no open position after the master close.','All 101 accounts become flat.','1. Close the master position.\n2. Read all 101 accounts.\n3. Verify no position remains.')
  started=time.monotonic();unfollow=each(lambda e:c.unfollow_master(e,mid,'real'),followers[:50],workers=50);links=c.get_copy_followers(master,'real');remaining={x['follower_client_id'] for x in links}
  details['unsubscribe50']=dict(statuses=[r['status_code'] for r in unfollow],remaining=len(remaining),elapsed_s=time.monotonic()-started)
  result('CTS-028','Unsubscribe 50 distinct followers concurrently',all(r['status_code']==200 for r in unfollow) and len(remaining)==50 and not(firstids&remaining),f'All fifty selected followers removed: {not bool(firstids&remaining)}. Remaining active links: {len(remaining)}.','Remove the selected fifty links and retain the other fifty.','1. Start flat with 100 active links.\n2. Send fifty unfollow requests concurrently.\n3. Verify selected links are absent and the other fifty remain.')
 finally:
  if master:
   c.bulk_squareoff(master,'real')
  def restore(m):
   e=m['email'];c.bulk_cancel(e,'real');c.bulk_squareoff(e,'real')
   if mid and e!=master:
    links=c.social_follows(e,'copy','real')
    if links['status_code']==200 and any(x.get('status')=='active' for x in links['data'].get('following',[])):c.unfollow_master(e,mid,'real')
   state=c.get_positions(e,'real')
   if 'error' in state or state['count'] or state['funds'].get('used_margin')!=0:return dict(email=e,ok=False)
   r=c.set_member_balance(m['member_id'],0,'real');state=c.get_positions(e,'real')
   links=c.social_follows(e,'copy','real')
   active=any(x.get('status')=='active' for x in links.get('data',{}).get('following',[])) if links['status_code']==200 else True
   return dict(email=e,ok=r['status_code']==200 and state.get('funds',{}).get('balance')==0 and not active)
  audits=each(restore,manifest);clean=all(x['ok'] for x in audits)
  (out/'fixture_after.json').write_text(json.dumps({'restored':clean,'accounts':audits,'retained':'Fresh accounts and master role retained; balances zeroed, links ended and positions closed.'},indent=2));(out/'details.json').write_text(json.dumps(details,indent=2));save();print('CLEANUP VERIFIED',clean,flush=True)
  if not clean:raise RuntimeError('Scale account cleanup needs attention')
if __name__=='__main__':main()
