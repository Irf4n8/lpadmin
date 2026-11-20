"""Small-order A-book and mixed-book checks on the explicitly authorized staging host."""
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


CASES=[
('AB001','Switch test accounts to A-book and verify read-back','Requested account books are A after successful update.'),
('AB002','A-book direct BUY market order','Small BUY is filled on the configured route or explicitly rejected without phantom exposure.'),
('AB003','A-book direct SELL market order','Small SELL is filled on the configured route or explicitly rejected without phantom exposure.'),
('AB004','A-book master to B-book followers','A filled A-book master order copies exactly once to each B-book follower.'),
('AB005','A-book master to A-book follower','A filled A-book master order copies exactly once to the A-book follower.'),
('AB006','B-book master to A-book follower','B-book master fill produces exactly one correctly routed A-book follower copy.'),
('AB007','A-book TP/SL changes','Valid TP/SL changes are acknowledged and visible on the position.'),
('AB008','A-book partial close','Closing half of .02 leaves .01 without negative quantity or side reversal.'),
('AB009','A-book master close propagation','Master close removes linked A-book and B-book copied positions.'),
('AB010','A-book concurrent duplicate close','One position closes once; no reversal, residual margin or server errors.'),
('AB011','A-book concurrent BUY/SELL','Two deliberate opposite orders create two distinct hedged positions.'),
('AB012','A-book concurrent order burst','Six deliberate orders have unique IDs and exactly six positions; no phantom duplicates.'),
('AB013','A-book pending LIMIT placement','Valid far-market LIMIT creates one pending order.'),
('AB014','A-book pending LIMIT modification','Existing pending price changes without recreating the ticket.'),
('AB015','A-book concurrent pending cancellation','Pending order disappears after cancellation; no 5xx or resurrection.'),
('AB016','Flat follower book switch while master holds a position','Flat follower can switch B to A despite an open position on its master.'),
('AB017','Independent external LP execution evidence','An external broker execution reference and independent reconciliation establish LP execution.'),
('AB018','Restore routing and account fixtures','Original books, balances, links and statuses restored; all eleven accounts flat.'),
]


class ABookRun(Run):
    def __init__(self,source):
        super().__init__(source)
        old=self.out
        self.out=ROOT/'reports/evidence'/('a_book_'+self.stamp)
        self.out.mkdir()
        old.rmdir()  # Empty directory created by the shared recorder, owned by this run.
        self.rows={tid:dict(tc_id=tid,description=description,preconditions='User-authorized staging; ten test followers; original state captured.',
                           steps=description,test_data='BLACK:EURUSD; qty .01/.02; instance real (hedging)',expected=expected,
                           actual='Not executed',status='NOT RUN',severity='—',defect_id='—',remarks='',evidence=[])
                   for tid,description,expected in CASES}
        self.books_before={}
        self.instances=[]
        self.route_observations=[]
        # No automatic resubmission after an uncertain financial write.
        original=self.c.request_with_retry
        def once(method,url,**kwargs):
            kwargs['max_attempts']=1
            return original(method,url,**kwargs)
        self.c.request_with_retry=once

    def record(self,tid,status,actual,remarks=''):
        row=self.rows[tid]
        row.update(status=status,actual=actual,remarks=remarks,evidence=[len(self.logs)],
                   severity='High' if status=='FAIL' else '—',defect_id='SPEC-'+tid if status=='FAIL' else '—')
        print(tid,status,actual[:350],flush=True)
        self.save()

    def save(self):
        counts=dict(Counter(r['status'] for r in self.rows.values()))
        report=dict(suite='A-book staging and mixed-book execution',started_at=self.start,
                    updated_at=datetime.now(timezone.utc).isoformat(),phase=self.phase,host=cfg.BASE_URL,
                    environment='staging (user-confirmed)',instance='real',instances=self.instances,
                    summary=counts,cases=list(self.rows.values()),evidence_directory=str(self.out),
                    external_lp_execution='Unverified unless an independent broker execution reference is recorded.',
                    route_observations=self.route_observations)
        (self.out/'execution.json').write_text(json.dumps(report,indent=2,default=str))
        (self.out/'requests.json').write_text(json.dumps(self.logs,indent=2,default=str))
        (ROOT/'reports/a_book_latest.json').write_text(json.dumps(report,indent=2,default=str))
        esc=lambda x:html.escape(str(x))
        columns=[('tc_id','TC ID'),('description','Test Case Description'),('preconditions','Pre-Conditions'),
                 ('steps','Test Steps'),('test_data','Test Data'),('expected','Expected Result'),('actual','Actual Result'),
                 ('status','Status'),('severity','Severity'),('defect_id','Defect ID'),('remarks','Remarks')]
        body=''.join('<tr>'+''.join('<td>'+esc(r[k])+'</td>' for k,_ in columns)+'</tr>' for r in self.rows.values())
        page='<!doctype html><html lang="en"><meta charset="utf-8"><title>A-book Staging Report</title><style>body{font:14px system-ui;margin:24px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd4df;padding:9px;text-align:left;vertical-align:top}th{background:#e8eef7;position:sticky;top:0}pre{white-space:pre-wrap}</style>'
        page+='<h1>A-book and Mixed-book Staging Tests</h1><p>'+esc(self.phase)+' | '+esc(counts)+'</p>'
        page+='<p>Routing configuration, internal OMS state and external broker execution are separate evidence levels. The instance inventory reported live_adapter=false / venue=paper; external LP fills require independent broker confirmation. B-book results in the main report remain separate.</p>'
        page+='<p><a href="master_spec_execution.html">Main report</a> · <a href="a_book_latest.json">A-book execution data</a> · <a href="evidence/'+esc(self.out.name)+'/requests.json">API evidence</a></p>'
        page+='<table><thead><tr>'+''.join('<th>'+label+'</th>' for _,label in columns)+'</tr></thead><tbody>'+body+'</tbody></table>'
        page+='<h2>Instance inventory</h2><pre>'+esc(json.dumps(self.instances,indent=2))+'</pre></html>'
        (ROOT/'reports/a_book_execution.html').write_text(page)

    def setbook(self,e,book):
        rr=self.c.set_member_book(self.snapshot[e]['member_id'],book)
        readback=self.c.get_member_books().get(e,{}).get('book')
        if rr['status_code']!=200 or readback!=book:
            raise RuntimeError(f'Book switch {e}->{book}: HTTP{rr["status_code"]}, readback={readback}, response={rr["data"]}')

    def probe(self,e=None,qty=.01,side='BUY',**kwargs):
        rr=self.c.place_order(e or self.m,symbol='BLACK:EURUSD',qty=qty,side=side,instance='real',**kwargs)
        self.route_observations.append(dict(account=e or self.m,side=side,qty=qty,response=rr))
        return rr

    @staticmethod
    def market_id(rr):return rr.get('data',{}).get('order',{}).get('market_order_id') if isinstance(rr.get('data'),dict) else None

    def filled(self,e,rr):
        mid=self.market_id(rr)
        return bool(mid) and self.poll(lambda:any(p['market_order_id']==mid for p in self.positions(e)['positions']),timeout=8)

    def blocked(self,tid,response):
        status='FAIL' if response['status_code']>=500 else 'BLOCKED'
        self.record(tid,status,f'Order setup did not fill: HTTP {response["status_code"]}; response={str(response["data"])[:1200]}',
                    'No filled order is counted as a copy/concurrency pass. Check LP/gateway configuration or rejection reason.')

    def copying(self):
        # A -> B, all ten followers B-book.
        self.clean(); self.setbook(self.m,'a'); self.setbook(self.fs[0],'b')
        rr=self.probe(); mid=self.market_id(rr)
        if self.filled(self.m,rr):
            copied=self.poll(lambda:all(self.positions(e)['count']==1 for e in self.fs),timeout=8)
            counts={e:self.positions(e)['count'] for e in self.fs}
            self.record('AB004','PASS' if copied else 'FAIL',f'A-book master filled {mid}; B-book follower counts={counts}',
                        'Book selection read back; independent broker venue still requires LP evidence.')
            # Reproduce reported follower switch guard with a flat follower and an open master.
            self.c.bulk_squareoff(self.fs[-1],'real')
            flat=self.positions(self.fs[-1])['count']==0 and not self.pending(self.fs[-1])
            try:
                if not flat:raise RuntimeError('Follower could not be flattened')
                self.setbook(self.fs[-1],'a')
                self.record('AB016','PASS','Follower B->A switch succeeded while follower flat and master position open.')
            except Exception as exc:
                self.record('AB016','FAIL',str(exc))
        else:
            self.blocked('AB004',rr)
            self.record('AB016','BLOCKED','A-book master did not fill; required master-open/follower-flat setup unavailable.')
        self.clean(); self.setbook(self.fs[-1],'b'); self.setbook(self.fs[0],'a')
        # A -> A + B controls.
        rr=self.probe(); mid=self.market_id(rr)
        if self.filled(self.m,rr):
            copied=self.poll(lambda:self.positions(self.fs[0])['count']==1,timeout=8)
            self.record('AB005','PASS' if copied else 'FAIL',f'A-book master filled {mid}; A-book follower positions={self.positions(self.fs[0])["count"]}')
            close=self.c.bulk_squareoff(self.m,'real')
            flat=self.poll(lambda:all(self.positions(e)['count']==0 for e in self.accounts))
            self.record('AB009','PASS' if close['status_code']==200 and flat else 'FAIL',f'Master close HTTP{close["status_code"]}; all A/B accounts flat={bool(flat)}')
        else:
            self.blocked('AB005',rr)
            self.record('AB009','BLOCKED','No filled A-book master position to close.')
        self.clean(); self.setbook(self.m,'b')
        rr=self.probe(); mid=self.market_id(rr)
        if self.filled(self.m,rr):
            copied=self.poll(lambda:self.positions(self.fs[0])['count']==1,timeout=8)
            counts={e:self.positions(e)['count'] for e in self.fs}
            self.record('AB006','PASS' if copied else 'FAIL',f'B-book master filled {mid}; A-book follower count={counts[self.fs[0]]}; all follower counts={counts}',
                        'A-book follower must fill independently of healthy B-book controls.')
        else:self.blocked('AB006',rr)
        self.clean()

    def direct(self):
        f=self.fs[0]; self.setbook(f,'a')
        available=False
        for tid,side in [('AB002','BUY'),('AB003','SELL')]:
            self.clean(); rr=self.probe(f,qty=.02,side=side); mid=self.market_id(rr)
            filled=bool(mid) and self.poll(lambda:self.positions(f)['count']==1)
            if not filled:
                self.blocked(tid,rr)
                continue
            available=True
            self.record(tid,'PASS',f'A-book account accepted and shows one {side} position; order={mid}',
                        'Internal OMS acceptance; independent LP execution checked separately.')
        self.clean()
        if not available:
            for tid in ('AB007','AB008','AB010','AB011','AB012'):
                self.record(tid,'BLOCKED','No filled direct A-book market position; lifecycle/race precondition unavailable.')
            self.pending_checks(f)
            return
        rr=self.probe(f,qty=.02); mid=self.market_id(rr)
        if not mid:raise RuntimeError('A-book lifecycle setup rejected after successful probe')
        p=self.positions(f)['positions'][0]; px=p['current_price']
        tp=round(px*1.05,5); sl=round(px*.95,5)
        protection=self.c.set_position_protection(f,mid,tp=tp,sl=sl,instance='real')
        expected=sorted([('TP',tp),('SL',sl)])
        visible=self.poll(lambda:sorted((o['type'],o.get('trigger_price') or o.get('price')) for o in self.pending(f) if o['type'] in ('TP','SL'))==expected)
        self.record('AB007','PASS' if protection['status_code']==200 and visible else 'FAIL',f'TP/SL HTTP{protection["status_code"]}; both prices visible={bool(visible)}; response={protection["data"]}',
                    'API acknowledgment recorded; external broker protection acknowledgment not independently available.')
        partial=self.c.reduce_position(f,mid,.01,'real')
        q=self.quantity(f)
        self.record('AB008','PASS' if partial['status_code']==200 and q==.01 else 'FAIL',f'Partial-close HTTP{partial["status_code"]}; remaining signed quantity={q}')
        closes=self.burst(lambda _:self.c.squareoff_position(f,mid,'real'),8)
        final=self.positions(f)
        ok=all(r['status_code']<500 for r in closes) and final['count']==0 and final['funds']['used_margin']==0
        self.record('AB010','PASS' if ok else 'FAIL',f'Close HTTP statuses={[r["status_code"] for r in closes]}; remaining={final["count"]}; margin={final["funds"]["used_margin"]}',
                    'Position/HTTP invariant checked; independent broker cash ledger required for full double-credit reconciliation.')
        self.clean()
        rr=self.burst(lambda i:self.probe(f,side=['BUY','SELL'][i]),2)
        positions=self.positions(f)['positions']
        ok=all(r['status_code']==200 for r in rr) and len(positions)==2 and {p['side'] for p in positions}=={'BUY','SELL'}
        self.record('AB011','PASS' if ok else 'FAIL',f'HTTP={[r["status_code"] for r in rr]}; positions={[(p["side"],p["net_qty"]) for p in positions]}')
        self.clean(); rr=self.burst(lambda _:self.probe(f),6)
        mids=[self.market_id(r) for r in rr]; n=self.positions(f)['count']
        self.record('AB012','PASS' if all(mids) and len(set(mids))==6 and n==6 else 'FAIL',f'HTTP={[r["status_code"] for r in rr]}; unique IDs={len(set(mids))}; positions={n}')
        self.clean(); self.pending_checks(f,px)

    def pending_checks(self,f,price=1.0):
        self.clean(); target=round(price*.7,5)
        rr=self.probe(f,order_type='LIMIT',price=target)
        oid=rr.get('data',{}).get('order',{}).get('order_id') if isinstance(rr.get('data'),dict) else None
        if not oid:
            self.blocked('AB013',rr)
            for tid in ('AB014','AB015'):self.record(tid,'BLOCKED','A-book pending LIMIT was not created.')
            return
        self.record('AB013','PASS' if len(self.pending(f))==1 else 'FAIL',f'LIMIT HTTP{rr["status_code"]}; ticket={oid}; price={target}')
        new=round(target*.95,5)
        modify=self.c.oms(f,'PUT',f'/orders/{oid}/modify','real',json={'price':new})
        pending=self.pending(f)
        ok=modify['status_code']==200 and any(o['order_id']==oid and abs(o.get('price',0)-new)<1e-8 for o in pending)
        self.record('AB014','PASS' if ok else 'FAIL',f'Modify HTTP{modify["status_code"]}; target price={new}; pending tickets={[(o["order_id"],o.get("price")) for o in pending]}')
        cancels=self.burst(lambda _:self.c.cancel_order(f,oid,'real'),6)
        ok=all(r['status_code']<500 for r in cancels) and not self.pending(f)
        self.record('AB015','PASS' if ok else 'FAIL',f'Cancel HTTP statuses={[r["status_code"] for r in cancels]}; remaining pending={len(self.pending(f))}')
        self.clean()

    def execute_a(self):
        completed=False
        try:
            self.instances=self.c.get_instances(self.m)
            books=self.c.get_member_books()
            self.books_before={e:books[e]['book'] for e in self.accounts}
            self.prepare(); self.phase='RUNNING'; self.save()
            self.setbook(self.m,'a'); self.setbook(self.fs[0],'a')
            self.record('AB001','PASS','Master and follower1 switched B->A; each admin read-back returned book=a.')
            for name in ('copying','direct'):
                try:getattr(self,name)()
                except Exception as exc:
                    self.logs.append(dict(group=name,error=repr(exc)))
                    print('GROUP ERROR',name,repr(exc),flush=True)
                    self.save()
            self.record('AB017','BLOCKED','Independent LP trade history/execution references and broker ledger were not available through this test kit.',
                        'Instance inventory reports live_adapter=false, venue=paper. Internal FILLED records do not independently certify LP execution.')
            completed=True
        finally:
            self.phase='RESTORING'; self.save()
            try:
                if self.fixture_changed:
                    self.clean()
                    for e,book in self.books_before.items():self.setbook(e,book)
                    self.restore()
                    current=self.c.get_member_books()
                    restored=all(current[e]['book']==book for e,book in self.books_before.items())
                    audit=json.loads((self.out/'fixture_after.json').read_text())
                    audit['books_before']=self.books_before
                    audit['books_after']={e:current[e]['book'] for e in self.accounts}
                    audit['restored']=audit['restored'] and restored
                    (self.out/'fixture_after.json').write_text(json.dumps(audit,indent=2))
                    self.record('AB018','PASS' if audit['restored'] else 'FAIL','Original routing, balances, links and account status restored; all eleven accounts flat.' if audit['restored'] else 'Restoration read-back mismatch.')
                self.phase='COMPLETE' if completed else 'SETUP FAILED'
            except Exception as exc:
                self.phase='RESTORATION ERROR: '+str(exc)
                raise
            finally:self.save()
        print('SUMMARY',Counter(r['status'] for r in self.rows.values()),flush=True)
        print('EVIDENCE',self.out,flush=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--confirm-staging-a-book',action='store_true')
    parser.add_argument('--spec',required=True)
    args=parser.parse_args()
    if not args.confirm_staging_a_book or cfg.BASE_URL!='https://lpadmin.blackfx.com':
        parser.error('Explicit staging A-book authorization and the authorized lpadmin host are required')
    ABookRun(args.spec).execute_a()


if __name__=='__main__':main()
