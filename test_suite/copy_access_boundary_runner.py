"""Read-only identity and admin access checks using dedicated Copy Trading followers."""
import argparse,json,sys
from pathlib import Path
from datetime import datetime,timezone
import requests
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from config.settings import BASE_URL,MEMBER_PASSWORD
from test_suite.client import BlackTraderClient

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--confirm-staging',action='store_true');a=ap.parse_args()
 if not a.confirm_staging or BASE_URL!='https://lpadmin.blackfx.com':ap.error('Authorized staging only')
 accounts=json.loads((ROOT/'reports/netting_fresh_accounts.json').read_text())['accounts'];followers=[x for x in accounts if x['intended_role'].startswith('follower')];stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'reports/evidence'/('copy_access_'+stamp);out.mkdir();c=BlackTraderClient(timeout=15);rows=[]
 def record(tid,desc,expected,ok,actual,steps):
  rows.append(dict(tc_id=tid,description=desc,preconditions='Two dedicated staging Copy Trading follower accounts exist.',steps=steps,test_data='Fresh follower 1 and follower 2; read-only requests; real-net.',expected=expected,actual=actual,status='PASS' if ok else 'FAIL',severity='High' if not ok else '—',defect_id='ACCESS-'+tid if not ok else '—',remarks='Limited to the named endpoint and supplied credential condition.',script='test_suite/copy_access_boundary_runner.py',reproduce_command='.venv/bin/python test_suite/copy_access_boundary_runner.py --confirm-staging',evidence=[str((out/'execution.json').relative_to(ROOT))]))
  print(tid,rows[-1]['status'],actual,flush=True)
 for i,acct in enumerate(followers):
  with requests.Session() as session:
   r=session.post(BASE_URL+'/api/auth/login',json={'email':acct['email'],'password':MEMBER_PASSWORD},timeout=15)
   if r.status_code!=200:raise RuntimeError('Dedicated follower login unavailable')
   me=session.get(BASE_URL+'/api/auth/me',timeout=15);body=me.json();text=json.dumps(body).lower();ok=me.status_code==200 and acct['email'].lower() in text and followers[1-i]['email'].lower() not in text
   record('CTA-'+str(i+1).zfill(3),'Return the correct identity for follower '+str(i+1),'Return this follower identity without the other follower identity.',ok,'Identity response HTTP '+str(me.status_code)+'; correct email='+str(ok),'1. Log in as this follower in a separate session.\n2. Read /api/auth/me.\n3. Compare account identity.')
   for j,path in enumerate(['/admin/api/members','/admin/api/instances']):
    rr=session.get(BASE_URL+path,headers={'Authorization':'Bearer '+c.get_trader_token(acct['email'])},timeout=15)
    # 404 is not proof of an authorization check.
    record(f'CTA-{10+i*2+j:03d}','Block follower access to '+path,'Reject a member session with HTTP 401 or 403.',rr.status_code in (401,403),'Member-session GET returned HTTP '+str(rr.status_code),'1. Authenticate as a follower.\n2. Request the named admin endpoint.\n3. Check rejection.')
 for i,headers in enumerate([{}, {'Authorization':'Bearer invalid-copy-test-token'}]):
  for j,path in enumerate(['/positions','/orders','/history','/copy/follows']):
   rr=requests.get(BASE_URL+'/v1/oms/real-net'+path,headers=headers,timeout=15)
   record(f'CTA-{20+i*4+j:03d}',('Reject anonymous' if i==0 else 'Reject invalid-token')+' access to '+path,'Reject with HTTP 401 or 403.',rr.status_code in (401,403),'Read returned HTTP '+str(rr.status_code),'1. Request the endpoint without a valid token.\n2. Check status; do not submit any write.')
 report=dict(suite='Copy Trading access boundaries',timestamp=stamp,host=BASE_URL,cases=rows)
 (out/'execution.json').write_text(json.dumps(report,indent=2));(ROOT/'reports/copy_access_latest.json').write_text(json.dumps(report,indent=2))
 print('EVIDENCE',out)
if __name__=='__main__':main()
