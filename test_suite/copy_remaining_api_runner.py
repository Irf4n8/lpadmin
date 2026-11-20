"""Additional executable master-spec cases; preserved prior evidence and guarded cleanup.
Only Copy Trading, authorized staging, ten-account existing QA cohort.
"""
import argparse,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from test_suite.staging_master_spec_runner import Run
from config import settings as cfg

class Completion(Run):
 def completion(self):
  # Master pending-order TP change while follower pending orders exist.
  self.baseline();self.opened();px=self.positions(self.m)['positions'][0]['current_price'];self.clean()
  price=round(px*.7,2);tp=round(px*1.3,2)
  rr=self.order(order_type='LIMIT',price=price,tp=round(px*1.2,2));oid=rr.get('data',{}).get('order',{}).get('order_id')
  if not oid:raise RuntimeError('Pending-order setup rejected')
  if not self.poll(lambda:all(len(self.pending(e))==1 for e in self.accounts)):raise RuntimeError('Pending copies not established')
  before={e:self.pending(e)[0]['order_id'] for e in self.accounts}
  change=self.c.oms(self.m,'PUT',f'/orders/{oid}/modify','real',json={'tp':tp})
  def match():return all(len(self.pending(e))==1 and self.pending(e)[0].get('tp')==tp and self.pending(e)[0]['order_id']==before[e] for e in self.accounts)
  ok=bool(self.poll(match,timeout=4))
  states={e:dict(count=len(self.pending(e)),tp=self.pending(e)[0].get('tp') if self.pending(e) else None,same_ticket=bool(self.pending(e)) and self.pending(e)[0]['order_id']==before[e]) for e in self.accounts}
  self.result('R007',change['status_code']==200 and ok,'Pending TP update HTTP '+str(change['status_code'])+'; requested TP='+str(tp)+'; account readbacks='+str(states),f'BTCUSDT LIMIT {price}; TP changed to {tp}',remarks='Pending-order schema does not expose a TP field. HTTP success alone cannot prove that protection changed; confirm the supported protection interface before classifying a product defect.',status=None if ok else 'IN PROGRESS')
  # Exact default-policy requirement: unfollow with two copied positions.
  self.baseline();f=self.fs[0];self.opened(qty=.01);self.opened(qty=.01)
  if not self.poll(lambda:self.positions(f)['count']==2):raise RuntimeError('Two copied positions not established')
  unfollow=self.c.unfollow_master(f,self.mid,'real');time.sleep(2);remaining=self.positions(f)['count'];active=any(x['follower_client_id']==self.snapshot[f]['member_id'] for x in self.c.get_copy_followers(self.m,'real'))
  self.result('C015',unfollow['status_code']==200 and remaining==0 and not active,f'Unfollow returned HTTP {unfollow["status_code"]}. Follower positions remaining after 2 seconds: {remaining}; active follower link: {active}.','Two open copied trades; default API unfollow action',remarks='Specification requires immediate closure. No selectable close-on-unfollow UI policy was supplied; this records the tested default API behavior.',status='FAIL' if remaining else 'IN PROGRESS')
  # Subscription/trade collisions: final-state observation, no fabricated internal cutoff proof.
  for subscribe,tid in [(True,'R013'),(False,'R014')]:
   observations=[]
   for i in range(3):
    self.baseline();f=self.fs[-1]
    if subscribe:self.c.unfollow_master(f,self.mid,'real')
    actions=[lambda:self.link(f)] if subscribe else [lambda:self.c.unfollow_master(f,self.mid,'real')]
    actions.append(lambda:self.order())
    rr=self.burst(lambda n:actions[n](),2);time.sleep(.5)
    count=self.positions(f)['count'];links=self.c.get_copy_followers(self.m,'real');active=any(x['follower_client_id']==self.snapshot[f]['member_id'] for x in links)
    observations.append(dict(round=i+1,http=[x['status_code'] for x in rr],positions=count,active=active))
    if count>1:break
   unsafe=any(x['positions']>1 for x in observations)
   self.result(tid,not unsafe,'Concurrent API request observations: '+str(observations),'Three repeats; one follow/unfollow request raced one master BUY',remarks='Server commit timestamps and fan-out ingestion cutoff are not observable through this API. Final-state subset only; the full deterministic ordering requirement remains unverified.',status='FAIL' if unsafe else 'IN PROGRESS')

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--spec',required=True);ap.add_argument('--confirm-staging',action='store_true');a=ap.parse_args()
 if not a.confirm_staging or cfg.BASE_URL!='https://lpadmin.blackfx.com':ap.error('Authorized staging only')
 prior=json.loads((ROOT/'reports/master_spec_latest.json').read_text())
 if prior['phase']!='COMPLETE':raise RuntimeError('Prior run must be complete')
 paths=list((ROOT/'reports/evidence').glob('master_spec_*/execution.json'));p=next(p for p in paths if json.loads(p.read_text()).get('started_at')==prior['started_at'])
 if not json.loads((p.parent/'fixture_after.json').read_text())['restored']:raise RuntimeError('Prior restoration unverified')
 run=Completion(a.spec);run.rows={r['tc_id']:r for r in prior['cases']};run.logs=json.loads((p.parent/'requests.json').read_text());run.prior_evidence=prior.get('prior_evidence',[])+[str(p.parent)]
 for tid in ('R007','C015','R013','R014'):
  run.rows['CT-'+tid]['script']='test_suite/copy_remaining_api_runner.py';run.rows['CT-'+tid]['reproduce_command']='.venv/bin/python test_suite/copy_remaining_api_runner.py --confirm-staging --spec <master-specification.txt>'
 run.execute(groups=('completion',))
if __name__=='__main__':main()
