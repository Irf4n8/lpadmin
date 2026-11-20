"""Evidence-first execution of the supplied 192-case specification on authorized staging.

Records every case, checkpoints after each group, and restores captured balances/links.
Does not claim server-internal, UI, billing or injected broker events from API observations.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import html
import hashlib
import json
from pathlib import Path
import re
import sys
from threading import Barrier, Lock
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import settings as cfg
from test_suite.client import BlackTraderClient
from requests.adapters import HTTPAdapter


def parse_spec(path):
    text = Path(path).read_text()
    rows = []
    for match in re.finditer(r'(?m)^(CT-[A-Z]\d{3})\s*\n(.*?)(?=^CT-[A-Z]\d{3}\s*$|\Z)', text, re.S):
        body = match[2]
        # The next section's introduction may follow the priority: stop at priority.
        priority = re.search(r'(?m)^(P[012])\s*$', body)
        if not priority:
            raise ValueError('Missing priority: ' + match[1])
        body = body[:priority.start()].strip()
        title, rest = body.split('\nPre:', 1)
        pre, rest = rest.split('\nSteps:', 1)
        steps, expected = rest.split('\nExpected:', 1)
        rows.append(dict(tc_id=match[1], description=title.strip(), preconditions=pre.strip(),
                         steps=steps.strip(), expected=expected.strip(), priority=priority[1],
                         test_data='Not executed', actual='Not executed', status='BLOCKED',
                         severity='—', defect_id='—', remarks='', evidence=[]))
    if len(rows) != 192 or len({r['tc_id'] for r in rows}) != 192:
        raise ValueError(f'Expected 192 distinct cases, got {len(rows)}')
    return rows


def default_blocker(tid):
    group = tid[3]
    if group in 'G':
        return 'Requires jurisdiction/KYC/licensing fixtures, compliance policies and audit access; not established in this run.'
    if group in 'I':
        return 'Requires infrastructure controls, broker simulator, deployment/queue/database access or scheduled reconciliation evidence.'
    if group in 'M':
        return 'Requires a controllable market/broker feed for the specified halt, gap, rollover, DST or stale-quote event.'
    if group in 'S':
        return 'Requires leaderboard/anti-abuse fixtures, analytics controls, billing or privileged policy verification.'
    if group in 'O':
        return 'Requires documented operational/admin workflow, audit pipeline or billing-job controls; not inferred from trading API.'
    if group == 'P':
        return 'Requires specified billing/commission/swap/replay/slippage fixture or browser state; not reproducible from ordinary trades alone.'
    if group == 'C':
        return 'Required risk configuration or broker mismatch fixture is not established in the available test API.'
    if group == 'F':
        return 'Requires onboarding/browser, broker mapping, pause/resume, disconnect or broker-specific fixture not established here.'
    if group == 'N':
        return 'Requires broker ownership/disabled-account/retry or broker-limit fixture not established here.'
    return 'Requires controlled in-flight fills, event injection, multiple masters, distributed workers or an explicit precedence policy.'


def parse_utc(value):
    value=re.sub(r'\.(\d+)',lambda m:'.'+m[1][:6].ljust(6,'0'),value)
    return datetime.fromisoformat(value.replace('Z','+00:00'))


class Run:
    def __init__(self, source):
        self.rows = {r['tc_id']: r for r in parse_spec(source)}
        for tid, row in self.rows.items():
            row['actual'] = default_blocker(tid)
        self.stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        self.out = ROOT / 'reports/evidence' / ('master_spec_' + self.stamp)
        self.out.mkdir(parents=True)
        self.c = BlackTraderClient(timeout=15, max_workers=12)
        # Do not silently replay financial writes while measuring idempotency.
        self.c.session.mount('https://', HTTPAdapter(max_retries=0, pool_maxsize=20))
        self.m = cfg.MASTER_EMAIL
        self.fs = [f'{cfg.DEFAULT_PREFIX}{i}@{cfg.DEFAULT_DOMAIN}' for i in range(1, 11)]
        self.accounts = [self.m] + self.fs
        self.mid = None
        self.snapshot = {}
        self.fixture_changed = False
        self.member_status_restore = {}
        self.logs = []
        self.log_lock = Lock()
        self.start = datetime.now(timezone.utc).isoformat()
        self.phase = 'INITIALIZING'
        original = self.c.request_with_retry
        def logged(method, url, **kwargs):
            # Record OMS/admin requests, excluding login credentials and bearer headers.
            t = time.monotonic()
            response = original(method, url, **kwargs)
            if not url.endswith('/login'):
                try:
                    data = response.json()
                except ValueError:
                    data = response.text[:3000]
                # The platform returns unpaginated multi-megabyte histories.
                # Retain full mutation responses, active orders and recent rows;
                # identify the complete read response with its digest and count.
                if method.upper()=='GET' and isinstance(data,dict):
                    data=dict(data)
                    for key in ('orders','history','members'):
                        if isinstance(data.get(key),list):
                            values=data[key]
                            selected=[x for x in values if x.get('state',x.get('status')) in ('PENDING','OPEN','NEW')]
                            if key=='members':
                                selected=[x for x in values if x.get('email') in self.accounts]
                            elif key=='history':
                                selected=values[:30]
                            else:
                                ids={x.get('order_id') for x in selected}
                                selected+= [x for x in values[:20] if x.get('order_id') not in ids]
                            data[key]=selected
                            data[key+'_evidence_metadata']=dict(total_rows=len(values),retained_rows=len(selected),
                                full_response_sha256=hashlib.sha256(response.content).hexdigest())
                with self.log_lock:
                    self.logs.append(dict(method=method, path=url.removeprefix(cfg.BASE_URL),
                                          payload=kwargs.get('json'), status=response.status_code,
                                          elapsed_s=round(time.monotonic()-t, 6), response=data))
            return response
        self.c.request_with_retry = logged

    def result(self, ids, ok, actual, data, remarks='', status=None):
        for tid in ids.split(','):
            row = self.rows['CT-' + tid]
            verdict = status or ('PASS' if ok else 'FAIL')
            row.update(status=verdict, actual=actual, test_data=data, remarks=remarks,
                       severity=('High' if row['priority']=='P0' else 'Medium') if verdict=='FAIL' else '—',
                       defect_id='SPEC-'+tid if verdict=='FAIL' else '—', evidence=[len(self.logs)])
            print(tid, verdict, actual[:230], flush=True)
        self.save()

    def save(self):
        counts = Counter(r['status'] for r in self.rows.values())
        report = dict(source='Supplied Master Test Specification v2.0; 192 cases',
                      started_at=self.start, updated_at=datetime.now(timezone.utc).isoformat(),
                      host=cfg.BASE_URL, environment='staging (user-confirmed)', instance='real',
                      symbol='BINANCE:BTCUSDT.P', phase=self.phase, summary=dict(counts),
                      release_status='NOT READY: full P0 verification incomplete', cases=list(self.rows.values()))
        report['prior_evidence']=getattr(self,'prior_evidence',[])
        (self.out/'execution.json').write_text(json.dumps(report, indent=2))
        (self.out/'requests.json').write_text(json.dumps(self.logs, indent=2, default=str))
        (ROOT/'reports/master_spec_latest.json').write_text(json.dumps(report, indent=2))
        columns=[('tc_id','TC ID'),('description','Test Case Description'),('preconditions','Pre-Conditions'),
                 ('steps','Test Steps'),('test_data','Test Data'),('expected','Expected Result'),('actual','Actual Result'),
                 ('status','Status'),('severity','Severity'),('defect_id','Defect ID'),('remarks','Remarks'),('priority','Priority')]
        esc=lambda x:html.escape(str(x))
        body=''.join('<tr>'+''.join('<td>'+esc(r[k])+'</td>' for k,_ in columns)+'</tr>' for r in self.rows.values())
        page='''<!doctype html><html lang="en"><meta charset="utf-8"><title>Master specification execution</title>
<style>body{font:14px system-ui;margin:24px;color:#172033}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd4df;padding:9px;text-align:left;vertical-align:top;white-space:pre-line}th{background:#e8eef7;position:sticky;top:0}input{padding:10px;width:420px}tr[hidden]{display:none}@media print{input{display:none}th{position:static}}</style>
<h1>Master Test Specification — Staging Execution</h1>'''
        page+='<p>'+esc(report['updated_at'])+' | '+esc(cfg.BASE_URL)+' | '+esc(self.phase)+'</p>'
        page+='<p><b>'+esc(dict(counts))+'</b></p><p>NOT READY: full P0 verification incomplete. BLOCKED cases are not passes. '
        page+='BTCUSDT is the executable symbol adaptation; exact FX/broker/market fixtures remain limited. Defect IDs are local report references, not external tickets.</p>'
        page+='<p><a href="evidence/'+esc(self.out.name)+'/execution.json">Execution JSON</a> · <a href="evidence/'+esc(self.out.name)+'/requests.json">API evidence</a> · <a href="evidence/'+esc(self.out.name)+'/fixture_after.json">Restoration audit</a></p>'
        page+='<h2>Execution summary</h2><table><tr><th>Priority</th><th>Total</th><th>Passed</th><th>Failed</th><th>Incomplete</th><th>Gate</th></tr>'
        for priority,threshold in [('P0',1),('P1',.95),('P2',.9)]:
            rows=[r for r in self.rows.values() if r['priority']==priority]
            passed=sum(r['status']=='PASS' for r in rows)
            failed=sum(r['status']=='FAIL' for r in rows)
            gate='MET' if rows and passed/len(rows)>=threshold else 'NOT MET'
            page+=f'<tr><td>{priority}</td><td>{len(rows)}</td><td>{passed}</td><td>{failed}</td><td>{len(rows)-passed-failed}</td><td>{gate} ({threshold:.0%} required)</td></tr>'
        page+='</table><h2>Test case execution table</h2>'
        page+='<input aria-label="Filter cases" placeholder="Filter by ID, result, or text" oninput="for(const r of document.querySelectorAll(\'tbody tr\'))r.hidden=!r.textContent.toLowerCase().includes(this.value.toLowerCase())">'
        page+='<table><thead><tr>'+''.join('<th>'+v+'</th>' for _,v in columns)+'</tr></thead><tbody>'+body+'</tbody></table>'
        page+='<h2>Status legend</h2><p>PASS: observed checks met. FAIL: observed mismatch. BLOCKED: required access/fixture unavailable. IN PROGRESS: API portion exercised but full requirement unverified.</p>'
        page+='<h2>Updated go-live plan</h2><table><tr><th>Phase</th><th>Current status</th><th>Remaining exit evidence</th></tr>'
        for phase,state,gap in [
            ('1 — Automated QA, stress and chaos','Incomplete','All 165 P0 scenarios must pass; infrastructure fault injection, 1,000-follower scale, DLQ and memory-leak checks remain unverified.'),
            ('2 — Staging pilot / paper trading','Not completed','14 consecutive days of independently reconciled broker/engine records, 10 masters / 50 users and HWM fee-cycle verification.'),
            ('3 — Controlled production canary','Not started / not authorized by staging task','Three vetted masters, follower/allocation caps, live slippage, dispute monitoring and measured MTTR; separate production authorization required.'),
            ('4 — General availability','Blocked by previous gates','Approved compliance, operations and QA sign-offs; KYC/AML, incident response, daily reconciliation and 24/7 monitoring evidence.')]:
            page+='<tr><td>'+esc(phase)+'</td><td>'+esc(state)+'</td><td>'+esc(gap)+'</td></tr>'
        page+='</table><p>Durations in the supplied plan are targets, not elapsed test evidence. Staging API passes do not certify legal compliance or production readiness.</p>'
        page+='<h2>Sign-off</h2><p>Test execution: Codex; QA Lead: pending; Project Manager: pending.</p></html>'
        if (ROOT/'reports/bug_register.json').exists():
            register=json.loads((ROOT/'reports/bug_register.json').read_text())
            page=page.replace('</html>','<h2>Additional reported bugs</h2><p>'+str(register['user_reported_count'])+' user-reported entries are recorded in the <a href="bug_register.html">bug register</a>. These reports do not automatically change executed test verdicts. Original dates, screenshots and verification status are preserved.</p></html>')
        if (ROOT/'reports/network_browser_race_cases.json').exists():
            supplement=json.loads((ROOT/'reports/network_browser_race_cases.json').read_text())
            page=page.replace('</html>','<h2>Additional race and network test plan</h2><p><a href="network_browser_race_cases.html">'+str(supplement['total_cases'])+' browser, network, copy-trading and algo race cases</a> added to the report. All are NOT RUN; related API checks are cross-referenced without claiming browser/network coverage. Combined catalogue: '+str(len(self.rows)+supplement['total_cases'])+' cases. The original 192-case verdicts remain unchanged.</p></html>')
        if (ROOT/'reports/a_book_latest.json').exists():
            a_book=json.loads((ROOT/'reports/a_book_latest.json').read_text())
            page=page.replace('</html>','<h2>A-book and mixed-book execution</h2><p><a href="a_book_execution.html">A-book report</a>: '+html.escape(str(a_book['summary']))+'. Original master-matrix results above reflect the B-book baseline. A-book routing variants are reported separately. Independent LP broker execution remains unverified unless explicit broker evidence is present.</p></html>')
        if (ROOT/'reports/netting_latest.json').exists():
            net=json.loads((ROOT/'reports/netting_latest.json').read_text())
            page=page.replace('</html>','<h2>Copy Trading netting execution</h2><p><a href="netting_execution.html">Fresh-account netting report and per-case script commands</a>: '+html.escape(str(net.get('functional_summary',net['summary'])))+'. Current execution scope is Copy Trading only; MAM and PAMM are excluded. Existing manual plans and reported bugs are retained as historical requirements, not newly executed tests.</p></html>')
        if (ROOT/'reports/reproduction_commands.json').exists():
            page=page.replace('</html>','<h2>Reproducible automation</h2><p><a href="reproduction_commands.html">Scripts and reproduction commands for executed checks</a>. Manual-only/unexecuted requirements are not represented as automated passes. Source snapshots are included in the package without credentials.</p></html>')
        if (ROOT/'reports/copy_trading_execution_table.html').exists():
            page=page.replace('</html>','<h2>Requested execution-table format</h2><p><a href="copy_trading_execution_table.html">Copy Trading report in the supplied eleven-column format</a>. The Excel version includes a separate scripts/evidence sheet. Partial observations and unexecuted requirements remain distinct from complete passes.</p></html>')
        (ROOT/'reports/master_spec_execution.html').write_text(page)

    def positions(self, e):
        data=self.c.get_positions(e,'real')
        if 'error' in data or not data.get('success', True):
            raise RuntimeError('Position read failed: '+str(data))
        return data

    def pending(self,e):
        data=self.c.get_orders(e,'real')
        if 'error' in data:
            raise RuntimeError('Order read failed: '+str(data))
        return [o for o in data.get('orders',[]) if o.get('state',o.get('status')) in ('PENDING','OPEN','NEW')]

    def poll(self, fn, timeout=10):
        end=time.monotonic()+timeout
        while True:
            result=fn()
            if result or time.monotonic()>=end:
                return result
            time.sleep(.15)

    def quantity(self,e):
        return round(sum(p['net_qty']*(1 if p['side']=='BUY' else -1) for p in self.positions(e)['positions']),8)

    def each(self, fn, items=None):
        with ThreadPoolExecutor(max_workers=12) as ex:
            return list(ex.map(fn, items or self.fs))

    def burst(self, fn, n):
        gate=Barrier(n)
        def act(i):
            gate.wait(timeout=10)
            return fn(i)
        with ThreadPoolExecutor(max_workers=n) as ex:
            return list(ex.map(act,range(n)))

    def clean(self):
        for e in self.accounts:
            result=self.c.bulk_cancel(e,'real')
            if result['status_code']!=200:
                raise RuntimeError('Cancel cleanup failed: '+str(result))
        self.c.bulk_squareoff(self.m,'real')
        self.each(lambda e:self.c.bulk_squareoff(e,'real'))
        if not self.poll(lambda:all(self.positions(e)['count']==0 and not self.pending(e) for e in self.accounts)):
            raise RuntimeError('Cleanup could not verify flat accounts')

    def link(self,e,mult=1,method='multiplier'):
        return self.c.follow_master(e,self.mid,'real',method=method,multiplier=mult)

    def baseline(self):
        self.clean()
        results=self.each(lambda e:self.link(e))
        if not all(r['status_code']==200 for r in results):
            raise RuntimeError('Baseline follow failed')

    def order(self,e=None,qty=.01,side='BUY',**kw):
        return self.c.place_order(e or self.m,qty=qty,side=side,instance='real',**kw)

    def opened(self,qty=.01,side='BUY'):
        r=self.order(qty=qty,side=side)
        if r['status_code']!=200:
            raise RuntimeError('Master setup rejected: '+str(r))
        if not self.poll(lambda:all(self.positions(e)['count'] for e in self.accounts)):
            raise RuntimeError('Missing setup copies')
        return r['data']['order']['market_order_id']

    def prepare(self):
        members={m['email']:m for m in self.c.get_admin_members()}
        if any(e not in members for e in self.accounts):
            raise RuntimeError('Ten configured staging followers required')
        if any(members[e].get('book')!='b' for e in self.accounts):
            raise RuntimeError('Test cohort must use B-book routing')
        self.mid=members[self.m]['member_id']
        links=self.c.get_copy_followers(self.m,'real',active_only=False)
        active=[x for x in links if x['status']=='active' and x['instance']=='real']
        expected={members[e]['member_id'] for e in self.fs}
        if {x['follower_client_id'] for x in active}!=expected:
            raise RuntimeError('Active copy topology differs from the intended ten-account cohort')
        for e in self.accounts:
            state=self.positions(e)
            if state['count'] or self.pending(e):
                raise RuntimeError('Pre-existing exposure: '+e+'; refusing to erase unrelated test state')
            self.snapshot[e]=dict(member_id=members[e]['member_id'],funds=state['funds'],status=members[e].get('status'))
        self.snapshot['links']=active
        (self.out/'fixture_before.json').write_text(json.dumps(self.snapshot,indent=2))
        self.fixture_changed = True
        for e in self.accounts:
            r=self.c.set_member_balance(members[e]['member_id'],100000000,'real')
            if r['status_code']!=200:
                raise RuntimeError('Fixture funding failed: '+e)
        self.baseline()

    def lifecycle(self):
        for side,tid in [('BUY','F006'),('SELL','F007')]:
            self.baseline(); mid=self.opened(side=side)
            qs=self.each(self.quantity)
            self.result(tid,all(q==(.01 if side=='BUY' else -.01) for q in qs),
                        f'{side} accepted; ten follower quantities={qs}; master order={mid}', 'BTCUSDT qty 0.01; multiplier 1x',
                        'Symbol and lot adapted from FX examples; broker-external execution/slippage SLA not certified.')
        self.baseline(); mid=self.opened(qty=.04)
        rr=self.c.reduce_position(self.m,mid,.02,'real')
        self.poll(lambda:all(self.quantity(e)==.02 for e in self.accounts))
        self.result('F013',rr['status_code']==200 and all(self.quantity(e)==.02 for e in self.accounts),
                    'Master and ten followers reduced 0.04 to 0.02', 'Master/followers 1x; 50% close',
                    'Specified 0.5x ratio is separately exercised by C002; this run verifies equal-ratio partial close.')
        self.c.squareoff_position(self.m,mid,'real')
        ok=self.poll(lambda:all(self.positions(e)['count']==0 for e in self.accounts))
        self.result('F012',ok,'Master close left all eleven accounts flat','Close remaining 0.02')
        self.baseline(); mids=[self.opened() for _ in range(3)]
        self.result('R011',len(set(mids))==3 and all(self.positions(e)['count']==3 for e in self.accounts),
                    'Three distinct same-symbol tickets on master and ten followers','3 sequential BTCUSDT orders',
                    'One-second spacing not forced; ticket separation exercised.',status='IN PROGRESS')
        self.result('F017',True,'Three same-symbol positions copied; distinct-symbol requirement not exercised',
                    'BTCUSDT only',status='IN PROGRESS')
        self.baseline(); self.opened(); self.c.bulk_squareoff(self.fs[0],'real'); self.c.bulk_squareoff(self.m,'real')
        ok=self.poll(lambda:all(self.positions(e)['count']==0 for e in self.accounts))
        self.result('F025',ok,'Manual follower close followed by master close; no remaining exposure','One copied position')

    def pending_tests(self):
        self.baseline(); self.opened(); price=self.positions(self.m)['positions'][0]['current_price']; self.clean()
        for kind,tid,factor in [('LIMIT','F008',.7),('STOP','F009',1.3)]:
            self.baseline(); target=round(price*factor,2)
            rr=self.order(order_type=kind,price=target); oid=rr.get('data',{}).get('order',{}).get('order_id')
            ok=bool(oid) and self.poll(lambda:all(len(self.pending(e))==1 for e in self.accounts))
            self.result(tid,ok,f'{kind} HTTP {rr["status_code"]}; mirrored pending counts='+str([len(self.pending(e)) for e in self.accounts]),f'BTCUSDT 0.01; price {target}')
            if kind=='LIMIT' and oid:
                before={e:self.pending(e)[0]['order_id'] for e in self.fs}
                new=round(target*.95,2)
                r=self.c.oms(self.m,'PUT',f'/orders/{oid}/modify','real',json={'price':new})
                def matching():
                    return all(any(abs(o.get('price',0)-new)<.001 for o in self.pending(e)) for e in self.fs)
                changed=self.poll(matching)
                stable=all(self.pending(e) and self.pending(e)[0]['order_id']==before[e] for e in self.fs)
                self.result('F010',r['status_code']==200 and changed and stable,
                            f'Modify HTTP {r["status_code"]}; all follower prices match={bool(changed)}; tickets retained={stable}',f'Limit price {target} -> {new}')
                r=self.c.cancel_order(self.m,oid,'real')
                empty=self.poll(lambda:not any(self.pending(e) for e in self.accounts))
                self.result('F011',r['status_code']==200 and empty,'Master cancellation; no pending orders across eleven accounts','Cancel copied LIMIT')
        self.clean()

    def protections(self):
        self.baseline(); mid=self.opened(); p=self.positions(self.m)['positions'][0]; px=p['current_price']
        def values(e):
            return sorted((o['type'],o.get('trigger_price') or o.get('price')) for o in self.pending(e) if o['type'] in ('TP','SL'))
        def apply(tp,sl,tid):
            rr=self.c.set_position_protection(self.m,mid,tp=tp,sl=sl,instance='real')
            want=sorted([('TP',tp),('SL',sl)])
            ok=self.poll(lambda:all(values(e)==want for e in self.accounts))
            self.result(tid,rr['status_code']==200 and ok,f'HTTP {rr["status_code"]}; expected={want}; follower sample={values(self.fs[0])}',f'TP {tp}; SL {sl}')
        tp=round(px*1.2,2); sl=round(px*.8,2)
        apply(tp,sl,'F014'); apply(round(tp*1.05,2),sl,'F015')
        tp=round(tp*1.05,2); sl1=round(sl*.98,2); sl2=round(sl*.96,2)
        self.c.set_position_protection(self.m,mid,tp=tp,sl=sl1,instance='real'); time.sleep(.05)
        rr=self.c.set_position_protection(self.m,mid,tp=tp,sl=sl2,instance='real')
        ok=self.poll(lambda:all(values(e)==sorted([('TP',tp),('SL',sl2)]) for e in self.accounts))
        self.result('R008',rr['status_code']==200 and ok,'All follower SL values converge to the second update',f'SL {sl1} -> {sl2}; 50ms client gap')

    def sizing(self):
        self.baseline(); f=self.fs[0]; self.link(f,.5); self.opened(qty=.04)
        self.result('C002',self.quantity(f)==.02,f'Master 0.04; follower={self.quantity(f)}','Multiplier 0.5x')
        self.link(f,2); before=self.quantity(f); self.opened(qty=.02); after=self.quantity(f)
        self.c.bulk_squareoff(self.m,'real'); closed=self.poll(lambda:not self.positions(f)['positions'])
        self.result('C014',before==.02 and after==.06 and closed,
                    f'Existing qty={before}; after new 2x trade={after}; full close propagated={bool(closed)}','0.5x -> 2x while open')
        self.result('R021,R049',True,'Between-trade setting change exercised; queued/in-flight snapshot cannot be observed through this API',
                    'Changed multiplier between acknowledged fills',status='IN PROGRESS')
        for mode,tid,balance,want in [('balance','C004',50000000,.02),('equity','C003',25000000,.01)]:
            self.baseline(); self.c.set_member_balance(self.snapshot[self.m]['member_id'],100000000,'real')
            self.c.set_member_balance(self.snapshot[f]['member_id'],balance,'real'); self.link(f,1,mode)
            self.opened(qty=.04); got=self.quantity(f)
            self.result(tid,abs(got-want)<1e-8,f'{mode}: master 100M, follower {balance}; actual qty={got}; expected={want}',f'Master qty 0.04; {mode} ratio')
            self.clean(); self.c.set_member_balance(self.snapshot[f]['member_id'],100000000,'real')
        self.baseline()
        for value,tid in [(0,'C007'),(-1,'C008')]:
            rr=self.link(f,value)
            self.result(tid,400<=rr['status_code']<500,f'HTTP {rr["status_code"]}; response={str(rr["data"])[:250]}',f'Multiplier {value}')
            self.link(f)

    def races(self):
        for tid,sides in [('R001',['BUY','BUY']),('R002',['BUY','SELL']),('R003',['BUY']*10)]:
            self.baseline(); start=time.monotonic()
            rr=self.burst(lambda i:self.order(side=sides[i]),len(sides)); elapsed=time.monotonic()-start
            ids=[r.get('data',{}).get('order',{}).get('order_id') for r in rr]
            copied=self.poll(lambda:all(self.positions(e)['count']==len(sides) for e in self.accounts))
            ok=all(r['status_code']==200 for r in rr) and len(set(ids))==len(sides) and copied
            self.result(tid,ok,f'{len(sides)} requests in {elapsed:.3f}s; HTTP={[r["status_code"] for r in rr]}; all copies={bool(copied)}',str(sides),
                        'Client barrier used; exact server arrival delta and deterministic queue ordering are not directly observable.',
                        status='IN PROGRESS' if tid=='R003' and ok else None)
        self.baseline(); self.opened(); px=self.positions(self.m)['positions'][0]['current_price']; self.clean()
        rr=self.order(order_type='LIMIT',price=round(px*.7,2)); oid=rr.get('data',{}).get('order',{}).get('order_id')
        time.sleep(.02); cr=self.c.cancel_order(self.m,oid,'real') if oid else {'status_code':0}
        ok=self.poll(lambda:not any(self.pending(e) for e in self.accounts))
        self.result('R004',rr['status_code']==200 and cr['status_code']==200 and ok,'Immediate LIMIT cancellation left no pending copies','20ms client gap after order ACK')
        self.baseline(); start=time.monotonic(); rr=self.order(); mid=rr.get('data',{}).get('order',{}).get('market_order_id')
        if not mid: raise RuntimeError('Rapid-close setup failed')
        close=self.c.squareoff_position(self.m,mid,'real'); elapsed=time.monotonic()-start
        flat=self.poll(lambda:all(self.positions(e)['count']==0 for e in self.accounts))
        self.result('R005',close['status_code']==200 and flat,f'Open+close elapsed={elapsed:.3f}s; all flat={bool(flat)}','Immediate close after open ACK',
                    status='IN PROGRESS' if elapsed>=.15 and flat else None)
        self.baseline(); self.opened()
        rr=self.burst(lambda i:self.c.bulk_squareoff([self.m,self.fs[0]][i],'real'),2)
        flat=self.poll(lambda:all(self.positions(e)['count']==0 for e in self.accounts))
        self.result('R032',flat and all(r['status_code']<500 for r in rr),'Concurrent master/follower close; all accounts flat; no 5xx','Two concurrent bulk close requests')
        self.baseline(); self.opened(); self.c.bulk_squareoff(self.m,'real'); self.opened(side='SELL')
        qs=self.each(self.quantity)
        self.result('R051',all(q==-.01 for q in qs),f'Close BUY; immediate SELL; follower net quantities={qs}','BUY 0.01 -> flat -> SELL 0.01')
        self.baseline(); self.opened(); manual=self.order(self.fs[0]); manual_id=manual['data']['order']['market_order_id']
        self.c.bulk_squareoff(self.m,'real')
        ok=self.poll(lambda:self.positions(self.fs[0])['count']==1)
        remaining=self.positions(self.fs[0])['positions']
        self.result('R053',ok and remaining[0]['market_order_id']==manual_id,'Master close preserved follower manual ticket='+str(manual_id),'Copied BUY plus manual BUY on follower')
        self.baseline(); self.opened(); f=self.fs[-1]
        rr=self.burst(lambda i:self.c.unfollow_master(f,self.mid,'real') if i==0 else self.c.bulk_squareoff(f,'real'),2)
        ok=self.poll(lambda:not self.positions(f)['positions'])
        active=[x for x in self.c.get_copy_followers(self.m,'real') if x['follower_name']==f.split('@')[0]]
        self.result('R075',ok and not active and all(r['status_code']<500 for r in rr),
                    f'Stop-copy + close-all: HTTP={[r["status_code"] for r in rr]}; positions=0; active links={len(active)}',f,
                    'Atomic transaction internals and absence of redundant internal orders require server trace.',
                    status='IN PROGRESS' if ok and not active and all(r['status_code']<500 for r in rr) else 'FAIL')
        self.link(f)

    def subscriptions(self):
        self.baseline(); f=self.fs[-1]; prefix=f.split('@')[0]
        u=self.c.unfollow_master(f,self.mid,'real'); self.order()
        self.poll(lambda:all(self.positions(e)['count']==1 for e in self.fs[:-1]))
        self.result('F005',u['status_code']==200 and self.positions(f)['count']==0,
                    'Unsubscribed account received no new master copy; other followers copied','Unsubscribe while flat',
                    'Browser policy-choice dialog not exercised.',status='IN PROGRESS')
        self.clean(); rr=self.burst(lambda _:self.link(f),2)
        links=[x for x in self.c.get_copy_followers(self.m,'real') if x['follower_name']==prefix]
        codes=sorted(x['status_code'] for x in rr)
        self.result('R019',len(links)==1 and codes==[200,409],f'HTTP={codes}; active link rows={len(links)}','Two simultaneous subscribe calls',
                    'Specification explicitly requires duplicate HTTP 409.')
        rr=self.burst(lambda _:self.c.unfollow_master(f,self.mid,'real'),2)
        links=[x for x in self.c.get_copy_followers(self.m,'real') if x['follower_name']==prefix]
        self.result('R020',not links and all(x['status_code']==200 for x in rr),
                    f'HTTP={[x["status_code"] for x in rr]}; active link rows={len(links)}','Two simultaneous unsubscribe calls')
        self.link(f); self.opened()
        self.result('F004',True,'API link active and receives copy; allocation/risk UI and internal subscription event not inspected',
                    'Existing onboarded account',status='IN PROGRESS')
        self.c.unfollow_master(f,self.mid,'real'); kept=self.positions(f)['count']; self.c.bulk_squareoff(self.m,'real')
        left=self.positions(f)['count']
        self.result('R018',True,f'Unsubscribe with open trade: immediately remaining={kept}; after master close={left}',
                    'Default API unsubscribe policy; no selected keep/close policy',status='IN PROGRESS')
        self.result('C015',True,'Close-on-unsubscribe policy selector not exposed by tested API; default policy observed only',
                    f'Immediate remaining={kept}; after master close={left}',status='IN PROGRESS')
        self.c.bulk_squareoff(f,'real'); self.link(f)

    def margin(self):
        self.baseline(); f=self.fs[4]; self.c.set_member_balance(self.snapshot[f]['member_id'],1,'real')
        before=self.positions(f)['funds']; rr=self.order(qty=.01)
        ok=self.poll(lambda:all(self.positions(e)['count']==1 for e in self.fs if e!=f))
        state=self.positions(f); accepted=rr['status_code']==200
        self.result('F018,C016,R025',accepted and ok and state['count']==0 and state['funds']['used_margin']==0,
                    f'Master HTTP={rr["status_code"]}; healthy followers filled={bool(ok)}; underfunded follower count={state["count"]}; margin={state["funds"]["used_margin"]}',
                    'Follower5 balance=1; master qty=0.01','Notification/audit-log delivery not verified.',status='IN PROGRESS' if accepted and ok and state['count']==0 else None)
        self.c.bulk_squareoff(self.m,'real'); state=self.positions(f)
        self.result('P009',accepted and state['count']==0 and state['funds']['balance']==before['balance'],
                    f'Rejected follower balance before={before["balance"]}, after={state["funds"]["balance"]}; no position',
                    'Master close after rejected follower copy')
        self.clean(); self.c.set_member_balance(self.snapshot[f]['member_id'],100000000,'real')
        self.baseline(); rr=self.order(qty=1e9)
        ok=rr['status_code']==400 and all(self.positions(e)['count']==0 for e in self.accounts)
        self.result('F019,N008',ok,f'Oversized master order HTTP={rr["status_code"]}; no copied positions; response={str(rr["data"])[:220]}',
                    'Master qty 1,000,000,000','Order rejection exercised; exact margin-level precondition not forced.',status='IN PROGRESS' if ok else None)

    def negative(self):
        self.baseline(); f=self.fs[0]
        rr=self.c.follow_master(f,'invalid_uuid_9999','real')
        self.result('N003',rr['status_code']==404,f'HTTP {rr["status_code"]}; {str(rr["data"])[:200]}','Invalid master ID',
                    'Specification requires 404, not merely any 4xx.')
        rr=self.c.follow_master(self.m,self.mid,'real')
        self.result('N010',400<=rr['status_code']<500,f'HTTP {rr["status_code"]}; {str(rr["data"])[:200]}','Master follows itself')
        if rr['status_code']==200:self.c.unfollow_master(self.m,self.mid,'real')
        fid=self.snapshot[f]['member_id']; rr=self.c.follow_master(self.m,fid,'real')
        self.result('N011',True,f'Master following existing follower returned HTTP {rr["status_code"]}; follower not promoted to master',
                    'Existing master/follower pair',status='IN PROGRESS')
        if rr['status_code']==200:self.c.unfollow_master(self.m,fid,'real')
        rr=[self.c.oms(None,'GET','/copy/follows','real'),self.c.oms(None,'GET','/positions','real'),
            self.c.oms(None,'POST','/orders','real',json={'symbol':'BINANCE:BTCUSDT.P','side':'BUY','type':'MARKET','qty':.01})]
        self.result('N012',all(x['status_code']==401 for x in rr),'Anonymous endpoint HTTP statuses='+str([x['status_code'] for x in rr]),
                    'No Authorization header')
        before=self.c.social_follows(f,'copy','real')
        rr=self.c.oms(f,'POST','/copy/follow','real',json={'master_client_id':self.mid,'method':'multiplier','multiplier':'abc'})
        after=self.c.social_follows(f,'copy','real')
        self.result('N014',rr['status_code']==422 and before==after,
                    f'Text multiplier HTTP={rr["status_code"]}; previous settings unchanged={before==after}',
                    'multiplier="abc"','Specification requires schema HTTP 422; applicable text-size input adaptation.')
        self.link(f)

    def accounting(self):
        self.baseline(); mid=self.opened(qty=.04); f=self.fs[0]
        p=self.positions(f)['positions'][0]; before=self.positions(f)['funds']
        rr=self.c.reduce_position(f,p['market_order_id'],.016,'real')
        state=self.positions(f); remaining=self.quantity(f); margin_after=state['funds']['used_margin']
        margin_ok=abs(margin_after-before['used_margin']*.6)<.05
        self.result('P003',remaining==.024 and margin_ok and rr['status_code']==200,
                    f'Closed 40%; remaining={remaining}; used margin {before["used_margin"]} -> {margin_after}; response={str(rr["data"])[:200]}',
                    'Follower qty .04; partial close .016','P&L fields retained in raw response; own execution prices used.')
        self.clean(); self.opened(qty=.01)
        p=self.positions(f)['positions'][0]; self.c.bulk_squareoff(self.m,'real')
        history=self.c.get_history(f,'real')
        if 'error' in history:raise RuntimeError('History API failed')
        rows=[h for h in history.get('history',[]) if h.get('position_id')==p['position_id']]
        self.result('F030',bool(rows),f'Closed copy history records for follower ticket: {len(rows)}',p['market_order_id'],
                    'History API checked; UI slippage columns and timestamps precision not fully inspected.',status='IN PROGRESS')

    def focused(self):
        self.baseline(); f=self.fs[0]; self.link(f,.5)
        mid=self.opened(qty=.04)
        rr=self.c.reduce_position(self.m,mid,.02,'real')
        ok=self.poll(lambda:self.quantity(self.m)==.02 and self.quantity(f)==.01)
        self.c.squareoff_position(self.m,mid,'real')
        flat=self.poll(lambda:all(self.positions(e)['count']==0 for e in self.accounts))
        self.result('F013',rr['status_code']==200 and ok and flat,
                    'Master .04 -> .02; 0.5x follower .02 -> .01; final master close left all accounts flat',
                    '0.5x follower; 50% master reduction','Lot quantities scaled from the supplied example.')
        self.baseline(); mids=[]
        for i in range(3):
            rr=self.order(symbol='BLACK:EURUSD',qty=.02)
            if rr['status_code']!=200:raise RuntimeError('FX setup rejected: '+str(rr))
            mids.append(rr['data']['order']['order_id'])
            if i<2:time.sleep(1)
        copied=self.poll(lambda:all(self.positions(e)['count']==3 for e in self.accounts))
        mapped=True
        for e in self.fs:
            oo=self.c.get_orders(e,'real')
            if 'error' in oo:raise RuntimeError('Order history read failed')
            children=[o for o in oo['orders'] if str(o.get('copy_ref','')).lstrip('-') in mids and o.get('state')=='FILLED']
            mapped=mapped and len(children)==3 and len({o['copy_ref'] for o in children})==3
        self.result('R011',copied and mapped,'Three EURUSD orders at one-second intervals; distinct master references copied once per follower',
                    'BLACK:EURUSD qty .02; 3 orders; ten followers')
        self.baseline(); accepted=[]
        for symbol in ('BLACK:EURUSD','BLACK:GBPUSD','BLACK:USDJPY'):
            rr=self.order(symbol=symbol,qty=.02)
            accepted.append(rr['status_code'])
        want={'BLACK:EURUSD','BLACK:GBPUSD','BLACK:USDJPY'}
        ok=self.poll(lambda:all({p['symbol'] for p in self.positions(e)['positions']}==want for e in self.accounts))
        self.result('F017',accepted==[200]*3 and ok,'EURUSD, GBPUSD and USDJPY independently copied to all ten followers',
                    'Three distinct FX symbols; .02 lots each')
        self.baseline(); self.link(f,.1)
        rr=self.order(qty=.001); mid=rr.get('data',{}).get('order',{}).get('order_id')
        time.sleep(1)
        q=self.quantity(f); oo=self.c.get_orders(f,'real')
        children=[o for o in oo.get('orders',[]) if str(o.get('copy_ref','')).lstrip('-')==mid]
        safe=rr['status_code']==200 and (q==.001 or q==0) and not any(o.get('state')=='REJECTED' for o in children)
        self.result('N005',safe,f'Computed .0001 below .001 broker minimum; actual follower qty={q}; child states={[o.get("state") for o in children]}',
                    'BTCUSDT master .001; follower 0.1x; min .001')
        self.baseline(); change=self.link(f,150)
        if change['status_code']==200:
            rr=self.order(symbol='BLACK:EURUSD',qty=1); mid=rr.get('data',{}).get('order',{}).get('order_id')
            time.sleep(1); ps=self.positions(f)['positions']; q=sum(p['net_qty'] for p in ps)
            ok=rr['status_code']==200 and q in (100,150) and all(p['net_qty']<=100 for p in ps)
            oo=self.c.get_orders(f,'real'); children=[o for o in oo.get('orders',[]) if str(o.get('copy_ref','')).lstrip('-')==mid]
            self.result('N006',ok,f'Calculated follower qty=150 above broker max=100; actual total={q}; position sizes={[p["net_qty"] for p in ps]}; child states={[o.get("state") for o in children]}',
                        'EURUSD master1; follower150x; published max100')
        else:
            self.result('N006',True,f'150x setup rejected HTTP {change["status_code"]}; above-max follower sizing not induced',
                        'EURUSD published max100',status='BLOCKED')
        self.baseline(); self.c.set_member_balance(self.snapshot[self.m]['member_id'],1,'real')
        before={e:self.positions(e)['funds']['balance'] for e in self.fs}
        rr=self.order(qty=.01)
        unchanged=all(self.positions(e)['count']==0 and self.positions(e)['funds']['balance']==before[e] for e in self.fs)
        margin_rejection='insufficient' in str(rr['data']).lower() and 'margin' in str(rr['data']).lower()
        self.result('N008,F019',rr['status_code']==400 and margin_rejection and unchanged,
                    f'Master balance1; HTTP {rr["status_code"]}; explicit insufficient-margin rejection={margin_rejection}; followers unchanged={unchanged}',
                    'BTCUSDT qty .01; master free margin1')
        self.c.set_member_balance(self.snapshot[self.m]['member_id'],100000000,'real')

    def financial(self):
        self.baseline(); f=self.fs[0]; self.link(f,.5)
        rr=self.order(symbol='BLACK:EURUSD',qty=.04)
        if rr['status_code']!=200:raise RuntimeError('FX accounting setup rejected')
        if not self.poll(lambda:all(self.positions(e)['count']==1 for e in self.accounts)):
            raise RuntimeError('Missing accounting setup copies')
        mp=self.positions(self.m)['positions'][0]; fp=self.positions(f)['positions'][0]
        self.c.bulk_squareoff(self.m,'real')
        self.poll(lambda:all(self.positions(e)['count']==0 for e in self.accounts))
        findings=[]; closed={}
        for e,p in [(self.m,mp),(f,fp)]:
            hs=self.c.get_history(e,'real')
            if 'error' in hs:raise RuntimeError('History read failed')
            rows=[h for h in hs.get('history',[]) if h.get('position_id')==p['position_id']]
            if not rows:raise RuntimeError('Closed history row missing')
            h=rows[0]; expected=(h['exit_price']-h['entry_price'])*h['qty']*100000*(1 if h['side']=='BUY' else -1)
            good=abs(h['realized_pnl']-expected)<=.011
            findings.append(dict(account=e,qty=h['qty'],expected=round(expected,6),actual=h['realized_pnl'],matches=good))
            closed[e]=h
        good=all(x['matches'] for x in findings) and closed[self.m]['qty']==.04 and closed[f]['qty']==.02
        self.result('P002',good,'Independent own-fill EURUSD gross P&L: '+str(findings),
                    'EURUSD contract100000; master .04; follower .02; 0.5x',
                    'Live fill prices and movement used instead of a fabricated fixed 100-pip market move; commission/net ledger assessed separately.')
        differing=any(closed[self.m][key]!=closed[f][key] for key in ('entry_price','exit_price'))
        self.result('P001',good and differing,f'Own-fill gross P&L matches={good}; different master/follower fill prices induced={differing}',
                    'EURUSD master .04; follower .02',
                    'The specified slippage-price difference requires a controlled feed if live fills are identical.',
                    status='BLOCKED' if good and not differing else None)
        mo=self.c.get_orders(self.m,'real')['orders']; fo=self.c.get_orders(f,'real')['orders']
        child=next(o for o in fo if o['order_id']==fp['market_order_id'])
        linked=str(child.get('copy_ref','')).lstrip('-')==mp['market_order_id']
        self.result('F030',True,f'History row matched by position_id; master reference valid={linked}; opened_at/closed execution time and own-fill gross P&L present',
                    'EURUSD history and order APIs','Browser History tab and displayed slippage columns remain blocked by unavailable browser host.',status='IN PROGRESS')
        self.baseline(); mid=self.opened(qty=.04); p=self.positions(f)['positions'][0]
        before=self.positions(f)['funds']; pr=self.c.reduce_position(f,p['market_order_id'],.016,'real')
        state=self.positions(f); hs=self.c.get_history(f,'real')
        rows=[h for h in hs.get('history',[]) if h.get('position_id')==p['position_id'] and abs(h.get('qty',0)-.016)<1e-9]
        math_ok=False
        if rows:
            h=rows[0]; expected=(h['exit_price']-h['entry_price'])*h['qty']
            math_ok=abs(h['realized_pnl']-expected)<=.011
        remaining=self.quantity(f); margin_ok=abs(state['funds']['used_margin']-before['used_margin']*.6)<.05
        self.result('P003',pr['status_code']==200 and remaining==.024 and margin_ok and math_ok,
                    f'Partial .016 booked in history={bool(rows)}; realized own-fill P&L matches={math_ok}; remaining={remaining}; used margin released40%={margin_ok}',
                    'BTCUSDT .04; close40%; history position_id correlation')


    def restore(self):
        if not self.fixture_changed:return
        for e,status in self.member_status_restore.items():
            rr=self.c.set_member_status(self.snapshot[e]['member_id'],status)
            if rr['status_code']!=200:raise RuntimeError('Member status restoration failed '+e)
        self.clean()
        for link in self.snapshot.get('links',[]):
            e=next(e for e in self.fs if self.snapshot[e]['member_id']==link['follower_client_id'])
            r=self.c.follow_master(e,self.mid,'real',link['method'],link['multiplier'],link.get('reverse',False),link.get('copy_mode','public'))
            if r['status_code']!=200:raise RuntimeError('Link restoration failed '+e)
        for e in self.accounts:
            if e in self.snapshot:
                r=self.c.set_member_balance(self.snapshot[e]['member_id'],self.snapshot[e]['funds']['balance'],'real')
                if r['status_code']!=200:raise RuntimeError('Balance restoration failed '+e)
        final={e:self.positions(e) for e in self.accounts}
        restored=all(final[e]['count']==0 and not self.pending(e) and final[e]['funds']['used_margin']==0
                     and abs(final[e]['funds']['balance']-self.snapshot[e]['funds']['balance'])<.001 for e in self.accounts)
        links=self.c.get_copy_followers(self.m,'real')
        keys=('follower_client_id','method','multiplier','reverse','copy_mode','instance','status')
        canonical=lambda xs:sorted(tuple(str(x.get(k)) for k in keys) for x in xs if x.get('instance')=='real')
        restored=restored and canonical(links)==canonical(self.snapshot['links'])
        member_statuses={m['email']:m.get('status') for m in self.c.get_admin_members() if m.get('email') in self.accounts}
        restored=restored and all(member_statuses.get(e)==status for e,status in self.member_status_restore.items())
        (self.out/'fixture_after.json').write_text(json.dumps(dict(accounts=final,links=links,member_statuses=member_statuses,restored=restored),indent=2))
        if not restored:raise RuntimeError('Read-back restoration verification failed')

    def administrative(self):
        self.baseline(); f=self.fs[0]; change=self.link(f,3)
        if change['status_code']==200 and self.rows['CT-N006']['status']!='PASS':
            rr=self.order(symbol='BLACK:EURUSD',qty=50)
            mid=rr.get('data',{}).get('order',{}).get('order_id')
            if mid:
                time.sleep(1); ps=self.positions(f)['positions']; total=sum(p['net_qty'] for p in ps)
                data=self.c.get_orders(f,'real')
                children=[o for o in data.get('orders',[]) if str(o.get('copy_ref','')).lstrip('-')==mid]
                ok=total in (100,150) and all(p['net_qty']<=100 for p in ps)
                self.result('N006',ok,f'Master50 at3x computes150; follower total={total}; position sizes={[p["net_qty"] for p in ps]}; child states={[o.get("state") for o in children]}',
                            'EURUSD published max100; valid3x multiplier; funded virtual staging accounts')
            else:
                self.result('N006',True,'Master fixture rejected: '+str(rr['data'])[:200], 'EURUSD master50 / follower3x',status='BLOCKED')
        self.baseline(); f=self.fs[0]; self.link(f,.5)
        rr=self.order(symbol='BLACK:EURUSD',qty=.02)
        mid=rr.get('data',{}).get('order',{}).get('order_id')
        if mid:
            self.poll(lambda:all(self.positions(e)['count']==1 for e in self.accounts))
            start=parse_utc(rr['data']['order']['updated_at']); observed=[]
            for e in self.fs:
                data=self.c.get_orders(e,'real')
                children=[o for o in data.get('orders',[]) if str(o.get('copy_ref','')).lstrip('-')==mid and o.get('state')=='FILLED']
                observed.append(dict(account=e,count=len(children),qty=children[0].get('filled_qty') if children else None,
                                     latency_ms=round((parse_utc(children[0]['updated_at'])-start).total_seconds()*1000,3) if children else None))
            good=all(x['count']==1 and x['qty']==(.01 if x['account']==f else .02) and x['latency_ms']<200 for x in observed)
            self.result('R023',good,'Ten-follower server fill timestamps: '+str(observed),
                        'EURUSD .02; follower1 .5x; others1x; SLA<200ms',
                        'Measured from master/follower OMS updated_at fields on the staging server; cross-broker clock accuracy not certified.')
        self.baseline(); f=self.fs[0]
        members={m['email']:m for m in self.c.get_admin_members()}
        old=members[f]['status']; self.member_status_restore[f]=old
        try:
            disabled=self.c.set_member_status(self.snapshot[f]['member_id'],'disabled')
            if disabled['status_code']!=200:
                self.result('N009',True,f'Could not establish disabled-account fixture: HTTP {disabled["status_code"]}',f,status='BLOCKED')
                return
            readback=next(m for m in self.c.get_admin_members() if m.get('email')==f)
            if readback.get('status')!='disabled':
                raise RuntimeError('Disabled-account fixture did not persist despite API acknowledgment')
            rr=self.order(qty=.01); mid=rr.get('data',{}).get('order',{}).get('order_id')
            if not mid:raise RuntimeError('Master order rejected in disabled-follower test')
            time.sleep(2)
        finally:
            restored=self.c.set_member_status(self.snapshot[f]['member_id'],old)
            if restored['status_code']!=200:raise RuntimeError('Immediate member status restoration failed')
        data=self.c.get_orders(f,'real')
        if 'error' in data:raise RuntimeError('Cannot inspect disabled-follower order evidence')
        rows=[o for o in data['orders'] if str(o.get('copy_ref','')).lstrip('-')==mid]
        fills=[o for o in rows if o.get('state')=='FILLED']
        self.result('N009',not fills,f'Disabled follower copy states={[o.get("state") for o in rows]}; filled copies={len(fills)}; member status restored={old}',
                    'Admin disables follower; valid master BUY while disabled',
                    'Auto-pause and notification delivery require separate verification.',status='BLOCKED' if not fills else 'FAIL')
        self.baseline(); f=self.fs[0]
        self.c.set_member_balance(self.snapshot[f]['member_id'],100,'real')
        rr=self.burst(lambda i:self.order(self.m if i==0 else f,qty=.01),2)
        time.sleep(1); state=self.positions(f); fd=state['funds']; count=state['count']
        safe=count==1 and fd['balance']>=0 and fd['used_margin']<=fd['equity']
        self.result('R054',safe,f'Manual order raced copy: follower positions={count}; used margin={fd["used_margin"]}; equity={fd["equity"]}; request HTTP={[x["status_code"] for x in rr]}',
                    'Follower balance100; each BTC order requires about61 margin',
                    'Manual trade used as competing margin consumer; two distinct strategies were not configured.',status='BLOCKED' if safe else 'FAIL')
        self.clean(); self.c.set_member_balance(self.snapshot[f]['member_id'],100000000,'real')

    def execute(self, groups=None):
        completed=False
        try:
            self.prepare(); self.phase='RUNNING'; self.save()
            for name in (groups or ('lifecycle','pending_tests','protections','sizing','races','subscriptions','margin','negative','accounting')):
                print('\nGROUP',name,flush=True)
                try:
                    self.baseline(); getattr(self,name)()
                except Exception as exc:
                    print('GROUP ERROR',name,repr(exc),flush=True)
                    self.logs.append(dict(group=name,error=repr(exc)))
                    self.save()
            for row in self.rows.values():
                if row['status']=='IN PROGRESS':
                    row['status']='BLOCKED'
                    row['coverage']='partial'
                    row['remarks']+=' Partial execution finished; the remaining specified criteria are unverified.'
            completed=True
        finally:
            self.phase='RESTORING'; self.save()
            try:
                self.restore(); self.phase='COMPLETE' if completed else 'SETUP FAILED'
            except Exception as exc:
                self.phase='RESTORATION ERROR: '+str(exc)
                raise
            finally:
                self.save()
        print('SUMMARY',Counter(r['status'] for r in self.rows.values()),flush=True)
        print('EVIDENCE',self.out,flush=True)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--spec',required=True)
    ap.add_argument('--confirm-staging',action='store_true')
    ap.add_argument('--extend-latest',action='store_true',help='Retain completed matrix and run focused FX/lot-limit follow-ups')
    ap.add_argument('--only-groups',choices=['administrative','financial','focused'],help='Run a selected additional Copy Trading group after --extend-latest')
    args=ap.parse_args()
    if not args.confirm_staging or cfg.BASE_URL!='https://lpadmin.blackfx.com':
        ap.error('Requires explicit staging confirmation for the authorized lpadmin host')
    prior=None
    if args.extend_latest:
        prior=json.loads((ROOT/'reports/master_spec_latest.json').read_text())
        if prior['phase']!='COMPLETE':ap.error('Prior run must be complete and restored')
        # Find the exact prior run through its start timestamp only after confirming completion.
        paths=sorted((ROOT/'reports/evidence').glob('master_spec_*/execution.json'),key=lambda p:p.stat().st_mtime,reverse=True)
        prior_path=next(p for p in paths if json.loads(p.read_text()).get('started_at')==prior['started_at'])
        if not json.loads((prior_path.parent/'fixture_after.json').read_text())['restored']:
            ap.error('Prior fixture restoration not verified')
    run=Run(args.spec)
    if prior:
        run.rows={r['tc_id']:r for r in prior['cases']}
        run.logs=json.loads((prior_path.parent/'requests.json').read_text())
        run.prior_evidence=prior.get('prior_evidence',[])+[str(prior_path.parent)]
    if args.only_groups and not prior:ap.error('--only-groups requires --extend-latest')
    run.execute(groups=(args.only_groups,) if args.only_groups else (('focused','financial') if prior else None))


if __name__=='__main__':
    main()
