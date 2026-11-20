"""Netting execution on user-requested fresh accounts; existing test accounts untouched."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import settings as cfg
from test_suite.staging_master_spec_runner import Run
from test_suite import netting_hedging_runner as legacy


SCENARIOS=[('N1','Open netted position'),('N2','Opposite order reduces exposure'),
           ('N3','Larger opposite order flips side'),('N4','Exact opposite order closes'),
           ('N5','TP/SL survives additions and copies'),('P1','Pending fan-out and cancellation'),
           ('C1','Concurrent mixed BUY/SELL'),('ISOLATION','Follower manual close does not close master'),
           ('ROUTING','Mixed A/B-book netting replication')]
EXPECTED={
    'N1':'BUY .03 produces one long position; followers hold .03 and .06 at1x/2x.',
    'N2':'BUY .03 then SELL .01 leaves one long .02; follower quantities .02/.04.',
    'N3':'BUY .03 then SELL .05 flips to one short .02; followers short .02/.04.',
    'N4':'BUY .02 then SELL .02 leaves master/followers flat with zero used margin.',
    'N5':'TP/SL remain after a net-position addition and both followers retain matching protection prices.',
    'P1':'Three pending LIMIT orders mirror to both followers; master cancellation removes all pending tickets.',
    'C1':'Master net equals accepted BUY minus accepted SELL; followers equal master times1x/2x, with at most one position per symbol and no5xx.',
    'ISOLATION':'Closing follower1 leaves it flat, master long .03 unchanged, and follower2 long .06 unchanged.',
    'ROUTING':'Each configured A/B account holds one correctly sized netted copy at its own routing book.',
    'SETUP':'Fresh netting master and two followers authenticated, funded and linked at1x/2x.',
    'RESTORE':'Positions/pending orders/used margin zero; original balances/books restored; newly created copy links ended.',
    'LP':'Independent broker execution references and cash-ledger reconciliation verify external LP execution.',
}


class NettingRun(Run):
    def __init__(self,source,manifest,books=('B','A'),only=(),recheck=False,repeat=1):
        super().__init__(source)
        old=self.out; self.out=ROOT/'reports/evidence'/('fresh_netting_'+self.stamp); self.out.mkdir(); old.rmdir()
        self.manifest=json.loads(Path(manifest).read_text())
        self.m=next(a['email'].lower() for a in self.manifest['accounts'] if a['intended_role']=='master')
        self.fs=[a['email'].lower() for a in self.manifest['accounts'] if a['intended_role'].startswith('follower')]
        if len(self.fs)!=2:raise RuntimeError('Requires two fresh followers')
        self.accounts=[self.m]+self.fs
        self.original_accounts=list(self.accounts)
        self.inst='real-net'; self.instances=[]; self.ids={}; self.before={}
        self.books=books;self.only=set(only);self.repeat=repeat
        self.publish='netting_recheck' if recheck else 'netting'
        self.rows={}
        for book in self.books:
            for sid,title in SCENARIOS:self.addrow('NT-'+book+'-'+sid,title,book+'-book')
        for tid,title in [('NT-SETUP','Fresh netting fixture setup'),('NT-RESTORE','Final clean-account and fixture audit'),('NT-LP','Independent external LP execution evidence')]:
            self.addrow(tid,title,'setup/audit')
        original=self.c.request_with_retry
        def once(method,url,**kwargs):
            kwargs['max_attempts']=1
            return original(method,url,**kwargs)
        self.c.request_with_retry=once
        # A rejected read must not silently turn into an empty account and a pass.
        for method in ('get_positions','get_orders','get_history'):
            raw=getattr(self.c,method)
            def checked(*args,_raw=raw,**kwargs):
                response=_raw(*args,**kwargs)
                if 'error' in response:raise RuntimeError(str(response['error']))
                return response
            setattr(self.c,method,checked)

    def addrow(self,tid,title,scope):
        self.rows[tid]=dict(tc_id=tid,description=title,preconditions='Fresh staging accounts; real-net mode; funded virtual wallets; no pre-existing exposure.',
                           steps=title,test_data='BLACK:EURUSD; base .01 lot; followers1x/2x; '+scope,
                           expected=EXPECTED[tid.split('-')[-1]],
                           actual='Not executed',status='NOT RUN',severity='—',defect_id='—',remarks='',evidence=[])
        self.rows[tid]['script']='test_suite/fresh_netting_staging_runner.py'
        if tid.startswith(('NT-B-','NT-A-')):
            book,sid=tid.split('-')[1:]
            self.rows[tid]['reproduce_command']=f'.venv/bin/python test_suite/fresh_netting_staging_runner.py --confirm-staging --accounts reports/netting_fresh_accounts.json --books {book.lower()} --only {sid} --recheck'
            if self.only and sid not in self.only:
                self.rows[tid].update(status='SKIPPED',actual='Not selected by --only')

    def record(self,tid,status,actual,remarks=''):
        self.rows[tid].update(status=status,actual=actual,remarks=remarks,evidence=[len(self.logs)],
                              severity='High' if status=='FAIL' else '—',defect_id='SPEC-'+tid if status=='FAIL' else '—')
        print(tid,status,actual[:400],flush=True);self.save()

    def save(self):
        functional=[r for k,r in self.rows.items() if k.startswith(('NT-B-','NT-A-'))]
        report=dict(suite='Fresh-account A/B-book netting execution',phase=self.phase,host=cfg.BASE_URL,
                    updated_at=datetime.now(timezone.utc).isoformat(),started_at=self.start,instance=self.inst,
                    summary=dict(Counter(r['status'] for r in self.rows.values())),
                    functional_summary=dict(Counter(r['status'] for r in functional)),
                    accounts=self.accounts,instances=self.instances,evidence_directory=str(self.out),
                    scope='Copy Trading only. Fresh accounts; two followers. No MAM, PAMM or algo execution. Internal OMS netting and book configuration; independent external LP fills are not certified.',
                    cases=list(self.rows.values()))
        (self.out/'execution.json').write_text(json.dumps(report,indent=2))
        (self.out/'requests.json').write_text(json.dumps(self.logs,indent=2,default=str))
        (ROOT/'reports'/(self.publish+'_latest.json')).write_text(json.dumps(report,indent=2))
        esc=lambda x:html.escape(str(x))
        columns=[('tc_id','TC ID'),('description','Test Case Description'),('preconditions','Pre-Conditions'),('steps','Test Steps'),
                 ('test_data','Test Data'),('expected','Expected Result'),('actual','Actual Result'),('status','Status'),
                 ('severity','Severity'),('defect_id','Defect ID'),('remarks','Remarks'),('script','Script'),('reproduce_command','Reproduce command')]
        for r in self.rows.values():r.setdefault('reproduce_command','.venv/bin/python test_suite/fresh_netting_staging_runner.py --confirm-staging --accounts reports/netting_fresh_accounts.json')
        page='<!doctype html><html lang="en"><meta charset="utf-8"><title>Fresh-account Netting Execution</title><style>body{font:14px system-ui;margin:24px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd4df;padding:9px;vertical-align:top;text-align:left}th{background:#e8eef7;position:sticky;top:0}pre{white-space:pre-wrap}</style><h1>Netting — Fresh Staging Accounts</h1>'
        page+='<p>'+esc(self.phase)+' | All checks: '+esc(report['summary'])+' | Functional A/B checks: '+esc(report['functional_summary'])+'</p>'
        page+='<p>'+esc(report['scope'])+'</p><p>Accounts: '+esc(', '.join(self.accounts))+'</p><p><a href="master_spec_execution.html">Main report</a> · <a href="'+self.publish+'_latest.json">Execution JSON</a> · <a href="evidence/'+self.out.name+'/requests.json">API evidence</a></p>'
        page+='<table><thead><tr>'+''.join('<th>'+label+'</th>' for _,label in columns)+'</tr></thead><tbody>'
        page+=''.join('<tr>'+''.join('<td>'+esc(r[k])+'</td>' for k,_ in columns)+'</tr>' for r in self.rows.values())+'</tbody></table>'
        page+='<p>Initial availability probes returned404; the runtime subsequently exposed real-net and paper-net during fresh-account verification. This timing does not prove account creation caused the runtime change. No hedging results are substituted for netting.</p></html>'
        (ROOT/'reports'/(self.publish+'_execution.html')).write_text(page)

    def positions(self,e):return self.c.get_positions(e,self.inst)
    def pending(self,e):return [o for o in self.c.get_orders(e,self.inst)['orders'] if o.get('state',o.get('status')) in ('PENDING','OPEN','NEW')]
    def clean(self):
        for e in self.accounts:self.c.bulk_cancel(e,self.inst)
        self.c.bulk_squareoff(self.m,self.inst)
        for e in self.accounts:self.c.bulk_squareoff(e,self.inst)
        if not self.poll(lambda:all(self.positions(e)['count']==0 and not self.pending(e) for e in self.accounts)):
            raise RuntimeError('Could not verify netting account cleanup')

    def setbook(self,e,book):
        rr=self.c.set_member_book(self.ids[e],book)
        got=self.c.get_member_books().get(e,{}).get('book')
        if rr['status_code']!=200 or got!=book:raise RuntimeError(f'Book switch failed {e}->{book}: {rr}, readback={got}')

    def context(self):return legacy.Ctx(self.c,self.inst,'BLACK:EURUSD',.01,self.m,self.fs,{self.fs[0]:1.,self.fs[1]:2.})

    def prepare(self):
        self.instances=self.c.get_instances(self.m)
        if not any(i['slug']==self.inst and i.get('netting') for i in self.instances):raise RuntimeError('Runtime does not expose real-net as netting')
        members={m['email'].lower():m for m in self.c.get_admin_members()}
        for e in self.accounts:
            if not e.startswith('netqa.'):raise RuntimeError('Refusing non-fresh QA account')
            state=self.positions(e)
            if state['count'] or self.pending(e):raise RuntimeError('Fresh account already holds exposure')
            self.ids[e]=members[e]['member_id'];self.before[e]=dict(book=members[e]['book'],balances=members[e].get('balances',{}),funds=state['funds'])
        self.mid=self.ids[self.m]
        (self.out/'fixture_before.json').write_text(json.dumps(self.before,indent=2))
        existing=self.c.social_follows(self.m,'copy',self.inst)
        if existing['status_code']!=200:raise RuntimeError('Cannot read fresh copy role')
        if not existing['data'].get('is_master'):
            rr=self.c.oms(self.m,'POST','/copy/master',self.inst,json={'kind':'copy_manager','display_name':'Netting QA Copy Master'})
            if rr['status_code']!=200:raise RuntimeError('Copy master setup rejected: '+str(rr))
        self.fixture_changed=True
        for e in self.accounts:
            rr=self.c.set_member_balance(self.ids[e],1000000,self.inst)
            if rr['status_code']!=200:raise RuntimeError('Netting fixture funding rejected: '+str(rr))
        for e,mult in zip(self.fs,(1.,2.)):
            rr=self.c.follow_master(e,self.mid,self.inst,multiplier=mult)
            if rr['status_code']!=200:raise RuntimeError('Netting follow rejected: '+str(rr))
        links=self.c.get_copy_followers(self.m,self.inst)
        if {x['follower_client_id'] for x in links if x['instance']==self.inst} != {self.ids[e] for e in self.fs}:
            raise RuntimeError('Fresh netting links failed read-back')
        self.record('NT-SETUP','PASS','Fresh copy master and two followers linked on real-net at1x/2x; virtual funding read back; no existing accounts modified.')

    def protection(self,ctx,k):
        legacy.need_ok(legacy.buy(ctx,.02),'BUY .02')
        self.poll(lambda:all(self.positions(e)['count']==1 for e in self.original_accounts))
        p=self.positions(self.m)['positions'][0]; px=p['current_price'];tp=round(px*1.1,5);sl=round(px*.9,5)
        rr=self.c.set_position_protection(self.m,p['market_order_id'],tp=tp,sl=sl,instance=self.inst)
        k.eq('Protection request HTTP',rr['status_code'],200)
        legacy.need_ok(legacy.buy(ctx,.01),'Add .01')
        def values(e):return sorted((o['type'],o.get('trigger_price') or o.get('price')) for o in self.pending(e) if o['type'] in ('TP','SL'))
        want=sorted([('TP',tp),('SL',sl)])
        self.poll(lambda:all(values(e)==want for e in self.original_accounts),timeout=8)
        k.true('Master TP/SL survive addition',values(self.m)==want,str(values(self.m)))
        for e in self.fs:k.true('Follower protection synchronized '+e,values(e)==want,str(values(e)))
        k.followers(ctx)

    def isolation(self,ctx,k):
        legacy.need_ok(legacy.buy(ctx,.03),'Open .03')
        k.followers(ctx)
        before=legacy.totals(ctx,self.m)
        follower=self.fs[0];p=self.positions(follower)['positions'][0]
        rr=self.c.squareoff_position(follower,p['market_order_id'],self.inst)
        k.eq('Follower close HTTP',rr['status_code'],200)
        k.eq('Master long unchanged',legacy.totals(ctx,self.m)[0],before[0])
        k.eq('Master short unchanged',legacy.totals(ctx,self.m)[1],before[1])
        k.eq('Other follower long preserved',legacy.totals(ctx,self.fs[1])[0],before[0]*2)
        k.eq('Closed follower positions',self.positions(follower)['count'],0)

    def race(self,ctx,k):
        results=legacy.parallel(lambda i:legacy.buy(ctx,.01) if i<6 else legacy.sell(ctx,.01),10)
        expected=round(sum((.01 if i<6 else -.01) for i,r in enumerate(results) if r['status_code']==200),8)
        rejected=[dict(index=i,side='BUY' if i<6 else 'SELL',http=r['status_code'],data=r['data']) for i,r in enumerate(results) if r['status_code']!=200]
        k.notes.append('HTTP statuses='+str([r['status_code'] for r in results])+'; explicit rejections='+str(rejected))
        k.true('No5xx under concurrency',all(r['status_code']<500 for r in results))
        time.sleep(3)
        b,s,n=legacy.totals(ctx,self.m)
        k.true('At most one netted position',n<=1,f'positions={n}')
        k.eq('Master net equals accepted BUY minus accepted SELL',round(b-s,8),expected)
        k.followers(ctx)

    def standard(self):
        for book in self.books:
            self.clean();self.setbook(self.m,book.lower());self.setbook(self.fs[0],book.lower());self.setbook(self.fs[1],'b')
            ctx=self.context()
            for title,fn in legacy.SCENARIOS_NET:
                sid=title.split()[0]
                if self.only and sid not in self.only:continue
                if sid=='N5':fn=self.protection
                if sid=='C1':fn=self.race
                results=[legacy.run(title,fn,ctx) for _ in range(self.repeat)]
                self.rows['NT-'+book+'-'+sid]['repetitions']=results
                status='FAIL' if any(r['status']=='FAIL' for r in results) else 'PASS'
                detail=' | '.join(f'round{i+1}: '+'; '.join(r['failures'] or r['notes']) for i,r in enumerate(results))
                self.record('NT-'+book+'-'+sid,status,detail,
                            'A-book phase uses A master/A follower1/B follower2. Broker execution beyond internal OMS remains independently unverified.' if book=='A' else '')
                self.clean()
            if not self.only or 'ISOLATION' in self.only:
                result=legacy.run('Follower manual close isolation',self.isolation,ctx)
                self.record('NT-'+book+'-ISOLATION',result['status'],'; '.join(result['failures'] or result['notes']))
            self.clean()
            if not self.only or 'ROUTING' in self.only:
                self.setbook(self.m,book.lower());self.setbook(self.fs[0],'a' if book=='B' else 'b')
                result=legacy.run('Mixed-book netting open',legacy.n1_open,ctx)
                self.record('NT-'+book+'-ROUTING',result['status'],'; '.join(result['failures'] or result['notes']),
                            'B master -> A follower1/B follower2.' if book=='B' else 'A master -> both B followers.')
                self.clean()

    def restore_fresh(self):
        if not self.fixture_changed:return
        self.clean()
        for e in self.fs:
            rr=self.c.oms(e,'GET','/copy/follows',self.inst)
            if any(x.get('status')=='active' for x in rr.get('data',{}).get('following',[])):
                self.c.unfollow_master(e,self.mid,self.inst)
        for e in self.accounts:
            self.setbook(e,self.before[e]['book'])
            rr=self.c.set_member_balance(self.ids[e],self.before[e]['funds']['balance'],self.inst)
            if rr['status_code']!=200:raise RuntimeError('Balance reset failed '+e)
        current=self.c.get_member_books();audit={}
        for e in self.accounts:
            state=self.positions(e); links={'copy':self.c.social_follows(e,'copy',self.inst)}
            active=sum(sum(x.get('status')=='active' for x in r.get('data',{}).get('following',[])) for r in links.values())
            ok=state['count']==0 and not self.pending(e) and state['funds']['used_margin']==0 and abs(state['funds']['balance']-self.before[e]['funds']['balance'])<.001 and current[e]['book']==self.before[e]['book'] and active==0
            audit[e]=dict(ok=ok,positions=state['count'],funds=state['funds'],book=current[e]['book'],active_follows=active)
        payload=dict(restored=all(v['ok'] for v in audit.values()),accounts=audit,
                     retained='Fresh test accounts and master roles retained; newly created follower links ended. Existing accounts never changed.')
        (self.out/'fixture_after.json').write_text(json.dumps(payload,indent=2))
        self.record('NT-RESTORE','PASS' if payload['restored'] else 'FAIL',str(payload))

    def execute_netting(self):
        complete=False
        try:
            self.prepare();self.phase='RUNNING';self.save()
            self.standard()
            self.record('NT-LP','BLOCKED','Independent external broker fill references and cash ledger were not available; instance venue is paper/live_adapter=false.')
            complete=True
        finally:
            self.phase='RESTORING';self.save()
            try:self.restore_fresh();self.phase='COMPLETE' if complete else 'SETUP/EXECUTION ERROR'
            except Exception as exc:self.phase='RESTORATION ERROR: '+str(exc);raise
            finally:self.save()
        print('SUMMARY',Counter(r['status'] for r in self.rows.values()),flush=True)
        print('EVIDENCE',self.out,flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--spec');p.add_argument('--accounts',required=True);p.add_argument('--confirm-staging',action='store_true')
    p.add_argument('--books',default='b,a',help='Comma-separated b,a routing phases')
    p.add_argument('--only',default='',help='Comma-separated '+','.join(sid for sid,_ in SCENARIOS))
    p.add_argument('--recheck',action='store_true',help='Publish a separate recheck report; preserve the complete baseline report')
    p.add_argument('--repeat',type=int,default=1,help='Repetitions of selected core scenarios;1..10')
    args=p.parse_args()
    if not args.confirm_staging or cfg.BASE_URL!='https://lpadmin.blackfx.com':p.error('Explicit authorized staging confirmation required')
    books=tuple(x.strip().upper() for x in args.books.split(',') if x.strip())
    only=tuple(x.strip().upper() for x in args.only.split(',') if x.strip())
    if not books or set(books)-{'A','B'} or set(only)-{sid for sid,_ in SCENARIOS} or not 1<=args.repeat<=10:p.error('Invalid book, Copy Trading scenario selector or repetition count')
    source=args.spec or next((str(p) for p in sorted((ROOT/'reports/evidence').glob('master_spec_*/master_specification_source.txt'))),None)
    if not source:p.error('No saved specification found; supply --spec')
    NettingRun(source,args.accounts,books,only,args.recheck,args.repeat).execute_netting()


if __name__=='__main__':main()
