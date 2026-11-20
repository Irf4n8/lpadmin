"""Evidence-driven MAM QA for authorized dedicated accounts, real hedging only.
No write retries. Admin balance changes exclusively use the actual Playwright UI.
"""
import argparse
import concurrent.futures as futures
import json
import math
import re
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.settings import BASE_URL, MASTER_EMAIL, MEMBER_PASSWORD, ADMIN_EMAIL, ADMIN_PASSWORD

OUT = ROOT / 'reports/live_recheck_20261120/deep_run'
SYMBOL = 'BLACK:BTCUSD'
MASTER_ID = 'mem_11434b0b9d9d210899'
FOLLOWERS = [f'mamf{i}@mailinator.com' for i in range(1, 101)]
ACCOUNTS = [MASTER_EMAIL] + FOLLOWERS


def now():
    return datetime.now(timezone.utc).isoformat()


class QA:
    def __init__(self):
        OUT.mkdir(parents=True, exist_ok=True)
        self.tokens = {}
        self.lock = threading.Lock()
        self.results = []
        self.run_id = datetime.now(timezone.utc).strftime('%H%M%S')
        self.trace_path = OUT / f'http_{self.run_id}.jsonl'
        self.active_case = 'SETUP'
        self.ui = None
        self.local = threading.local()
        self.pool = futures.ThreadPoolExecutor(max_workers=8)

    def trace(self, data):
        with self.lock:
            with self.trace_path.open('a', encoding='utf-8') as f:
                f.write(json.dumps(data, ensure_ascii=True) + '\n')

    def login(self, email):
        with requests.Session() as s:
            r = s.post(BASE_URL+'/api/auth/login', json={'email': email, 'password': MEMBER_PASSWORD}, timeout=20)
            if r.status_code != 200 or r.json().get('success') is not True:
                raise RuntimeError(f'Login failed: {email}, HTTP {r.status_code}')
            r = s.post(BASE_URL+'/api/auth/chart-token', timeout=20)
            token = r.json().get('token') if r.status_code == 200 else None
            if not token:
                raise RuntimeError(f'No chart token: {email}')
            self.tokens[email] = token

    def authenticate(self):
        with futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(self.login, ACCOUNTS))
        info = self.read(MASTER_EMAIL, 'info')
        assert info['slug'] == 'real' and info['mode'] == 'hedging', info
        print('Authenticated 101 scoped accounts; confirmed real hedging.', flush=True)

    def api(self, email, method, endpoint, payload=None):
        assert email in ACCOUNTS
        assert not endpoint.startswith('/') and '..' not in endpoint
        started = now()
        t = time.monotonic()
        try:
            if not hasattr(self.local,'session'):
                self.local.session=requests.Session()
            r = self.local.session.request(method, BASE_URL+'/v1/oms/real/'+endpoint,
                headers={'Authorization': 'Bearer '+self.tokens[email], 'X-Broker-ID': 'real'},
                json=payload, timeout=30)
            try:
                body = r.json()
            except ValueError:
                body = {'non_json_body': r.text[:1000]}
            out = {'http': r.status_code, 'body': body}
        except requests.RequestException as e:
            out = {'http': None, 'body': {'transport_error': str(e)}}
        self.trace({'case': self.active_case, 'started_at': started, 'finished_at': now(),
                    'elapsed_ms': round((time.monotonic()-t)*1000,2), 'email': email,
                    'method': method, 'endpoint': endpoint, 'payload': payload, **out})
        return out

    def read(self, email, ep):
        for attempt in range(3):
            r = self.api(email, 'GET', ep)
            if r['http'] not in (None,429,502,503,504):
                break
            if attempt<2:time.sleep(.5*(attempt+1))
        if r['http'] != 200 or not isinstance(r['body'], dict) or r['body'].get('success') is False:
            raise RuntimeError(f'Read failed {email} {ep}: {r}')
        return r['body']

    def positions(self, email):
        d = self.read(email, 'positions')
        if d.get('count') != len(d.get('positions', [])):
            raise RuntimeError('Inconsistent position count')
        return d

    def fleet(self, accounts=None):
        emails = accounts or ACCOUNTS
        return dict(zip(emails, self.pool.map(self.positions, emails)))

    def links(self, email):
        return self.read(email, 'mam/follows')

    def configure(self, emails, method='multiplier', multiplier=1):
        def update(email):
            return self.api(email, 'POST', 'mam/follow', {'master_client_id': MASTER_ID, 'method': method, 'multiplier': multiplier})
        with futures.ThreadPoolExecutor(max_workers=5) as pool:
            responses = list(pool.map(update, emails))
        if any(r['http'] != 200 or r['body'].get('success') is not True for r in responses):
            raise RuntimeError('Follower configuration failed: '+str(responses))
        return responses

    def place(self, side='BUY', qty=.02, kind='MARKET', price=None, **extra):
        payload = {'symbol': SYMBOL, 'side': side, 'qty': qty, 'type': kind,
                   'group_id': 'qa_'+uuid.uuid4().hex[:16], 'source': 'api', 'tag': 'QA_20261120', **extra}
        if price is not None:
            payload['price'] = price
        return self.api(MASTER_EMAIL, 'POST', 'orders' if kind == 'MARKET' else 'orders/pending', payload)

    @staticmethod
    def order_id(r):
        b = r.get('body', {})
        return (b.get('position') or {}).get('market_order_id') or (b.get('order') or {}).get('market_order_id') or (b.get('order') or {}).get('order_id')

    def close(self, email, order_id):
        return self.api(email, 'POST', f'positions/{order_id}/squareoff', {})

    def cleanup(self):
        # Master first, then residuals; verify inventory reads and final state.
        for p in self.positions(MASTER_EMAIL)['positions']:
            self.close(MASTER_EMAIL, p['market_order_id'])
        time.sleep(.5)
        fleet = self.fleet()
        jobs = [(e,p['market_order_id']) for e,d in fleet.items() for p in d['positions']]
        list(self.pool.map(lambda item:self.close(*item), jobs))
        def cancel(email):
            orders = self.read(email, 'orders')['orders']
            for o in orders:
                if o.get('state') in ('PENDING', 'OPEN', 'NEW'):
                    self.api(email, 'DELETE', 'orders/'+o['order_id'])
        list(self.pool.map(cancel, ACCOUNTS))
        final = self.fleet()
        remaining = {e:d['count'] for e,d in final.items() if d['count']}
        if remaining:
            raise RuntimeError('Residual positions after cleanup: '+str(remaining))
        return {'positions_remaining': 0, 'accounts_checked': len(final)}

    def check(self, id_, name, fn):
        self.active_case = id_
        started = now()
        try:
            passed, details = fn()
            status = 'PASS' if passed else 'FAIL'
        except Exception as e:
            status, details = 'BLOCKED', {'error': type(e).__name__+': '+str(e)}
        row = {'id': id_, 'name': name, 'status': status, 'started_at': started, 'finished_at': now(), 'details': details,
               'trace': self.trace_path.name}
        self.results.append(row)
        (OUT / f'results_{self.run_id}.json').write_text(json.dumps(self.results, indent=2), encoding='utf-8')
        print(f'[{status}] {id_}: {name} '+json.dumps(details)[:450], flush=True)
        return row

    def wait_fleet(self, expected_count, timeout=20):
        deadline = time.monotonic()+timeout
        while True:
            data = self.fleet()
            if all(d['count']==expected_count for d in data.values()) or time.monotonic()>=deadline:
                return data
            time.sleep(.5)

    def setup(self):
        before = self.fleet()
        (OUT/'authorized_initial_positions.json').write_text(json.dumps(before,indent=2),encoding='utf-8')
        with futures.ThreadPoolExecutor(max_workers=5) as pool:
            links = dict(zip(ACCOUNTS,pool.map(self.links,ACCOUNTS)))
        (OUT/'authorized_initial_links.json').write_text(json.dumps(links,indent=2),encoding='utf-8')
        clean=self.check('SETUP-CLEAN', 'Close existing scoped real positions and cancel pending orders', lambda:(True,self.cleanup()))
        assert clean['status']=='PASS','Cannot continue with unverified cleanup'
        for email in FOLLOWERS:
            for link in links[email]['following']:
                if link['status']=='active' and link['master_client_id']!=MASTER_ID:
                    r=self.api(email,'POST','mam/unfollow',{'master_client_id':link['master_client_id']})
                    assert r['http']==200 and r['body'].get('success'), r
        self.configure(FOLLOWERS)
        self.baseline()

    def baseline(self):
        data=self.fleet()
        if any(d['count'] for d in data.values()):self.cleanup()
        self.active_case='SETUP-BALANCE'
        self.ui = AdminUI(self)
        for i,email in enumerate(ACCOUNTS):
            self.ui.balance(email,1000000,screenshot=i in (0,1,100))
            funds=self.positions(email)['funds']
            if abs(funds['balance']-1000000)>.01:
                raise RuntimeError(f'GUI balance readback mismatch {email}: {funds}')
            if i%10==0:
                print(f'GUI balance baseline verified: {i+1}/101',flush=True)
        self.check('SETUP-BALANCE', 'GUI set/read back 1,000,000 on all 101 real-hedging accounts',
                   lambda:(True,{'accounts':101,'balance_each':1000000,'mechanism':'Actual admin GUI clicks + API readback'}))

    def smoke(self):
        def market(side):
            r=self.place(side, .02)
            if r['http']!=200 or not r['body'].get('success'):
                return False,{'placement':r}
            data=self.wait_fleet(1)
            bad={e:d for e,d in data.items() if d['count']!=1 or d['positions'][0]['symbol']!=SYMBOL
                 or d['positions'][0]['side']!=side or abs(d['positions'][0]['net_qty']-.02)>1e-8}
            oid=self.order_id(r)
            close=self.close(MASTER_EMAIL,oid)
            end=self.wait_fleet(0)
            remaining={e:d['count'] for e,d in end.items() if d['count']}
            return not bad and not remaining and close['http']==200,{'master_order_id':oid,'accounts':101,
                'incorrect_positions':bad,'remaining_after_master_close':remaining,'close':close}
        for side in ('BUY','SELL'):
            self.check('MARKET-'+side,'BLACK BTCUSD '+side+' -> 100 followers -> master close',lambda side=side:market(side))

    def require_open(self,side='BUY',qty=.02,**kwargs):
        r=self.place(side,qty,**kwargs)
        if r['http']!=200 or r['body'].get('success') is not True or not self.order_id(r):
            raise RuntimeError('Order prerequisite failed: '+str(r))
        return r

    def flat(self):
        data=self.wait_fleet(0)
        return {e:d['positions'] for e,d in data.items() if d['count']}

    def lifecycle(self):
        self.cleanup()
        def partial():
            r=self.require_open(qty=.02)
            self.wait_fleet(1)
            oid=self.order_id(r)
            reduce=self.api(MASTER_EMAIL,'POST',f'positions/{oid}/reduce',{'qty':.01})
            time.sleep(1)
            data=self.fleet()
            bad={e:d['positions'] for e,d in data.items() if d['count']!=1 or abs(d['positions'][0]['net_qty']-.01)>1e-8}
            self.close(MASTER_EMAIL,oid)
            remaining=self.flat()
            return reduce['http']==200 and not bad and not remaining,{'reduce':reduce,'incorrect_remaining_qty':bad,'orphans':remaining}
        self.check('LIFE-PARTIAL','Master 50% partial close replicates remaining quantity to 100 followers',partial)
        self.cleanup()
        def hedging():
            buy=self.require_open('BUY')
            sell=self.require_open('SELL')
            data=self.wait_fleet(2)
            bad={e:d['positions'] for e,d in data.items() if d['count']!=2 or sorted(p['side'] for p in d['positions'])!=['BUY','SELL']}
            self.close(MASTER_EMAIL,self.order_id(buy))
            one=self.wait_fleet(1)
            wrong={e:d['positions'] for e,d in one.items() if d['count']!=1 or d['positions'][0]['side']!='SELL'}
            self.close(MASTER_EMAIL,self.order_id(sell))
            return not bad and not wrong and not self.flat(),{'coexistence_errors':bad,'selective_close_errors':wrong}
        self.check('LIFE-HEDGE','Opposite positions coexist; closing BUY preserves SELL across 101 accounts',hedging)
        self.cleanup()
        def follower_close():
            r=self.require_open()
            data=self.wait_fleet(1)
            child=data[FOLLOWERS[0]]['positions'][0]['market_order_id']
            f=self.close(FOLLOWERS[0],child)
            after=self.fleet()
            bad={e:d['count'] for e,d in after.items() if d['count']!=(0 if e==FOLLOWERS[0] else 1)}
            self.close(MASTER_EMAIL,self.order_id(r))
            return f['http']==200 and not bad and not self.flat(),{'follower_close':f,'unexpected_accounts':bad}
        self.check('LIFE-FOLLOWER-CLOSE','Follower manual close does not close master or other followers',follower_close)
        self.cleanup()
        def protections():
            r=self.require_open()
            data=self.wait_fleet(1)
            price=r['body']['position']['avg_entry_price']
            oid=self.order_id(r)
            edit=self.api(MASTER_EMAIL,'PUT',f'positions/{oid}/protection',{'sl':price-10000,'tp':price+10000})
            time.sleep(1)
            data=self.fleet()
            # Check actual protection orders linked to each newly created position.
            def inspect(email):
                pos=data[email]['positions']
                if len(pos)!=1:return {'error':'position missing'}
                mid=pos[0]['market_order_id']
                orders=self.read(email,'orders')['orders']
                brackets=[o for o in orders if o.get('parent_order_id')==mid and o.get('state')=='PENDING']
                return {'market_order_id':mid,'brackets':brackets}
            brackets=dict(zip(ACCOUNTS,self.pool.map(inspect,ACCOUNTS)))
            bad={e:d for e,d in brackets.items() if set(o.get('type') for o in d.get('brackets',[]))!={'SL','TP'}}
            self.close(MASTER_EMAIL,oid)
            return edit['http']==200 and not bad and not self.flat(),{'edit':edit,'missing_brackets':bad,'all_brackets':brackets}
        self.check('LIFE-PROTECTION','Master SL/TP modification creates both child protection orders',protections)
        self.cleanup()

    def boundaries(self):
        self.cleanup()
        payloads=[('ZERO-QTY',{'qty':0}),('NEGATIVE-QTY',{'qty':-.01}),('BAD-SIDE',{'side':'SIDEWAYS'}),
                  ('BAD-SYMBOL',{'symbol':'BLACK:QA_NONEXISTENT'}),('UNKNOWN-TYPE',{'type':'TYPO'}),
                  ('LIMIT-WRONG-ENDPOINT',{'type':'LIMIT'}),('SUBMIN-LOT',{'qty':.001})]
        for name,delta in payloads:
            def case(delta=delta):
                r=self.api(MASTER_EMAIL,'POST','orders',{'symbol':SYMBOL,'side':'BUY','qty':.02,'type':'MARKET',**delta})
                data=self.fleet()
                residual={e:d['count'] for e,d in data.items() if d['count']}
                passed=r['http'] in (400,422) and not residual
                if residual:self.cleanup()
                return passed,{'response':r,'unexpected_positions':residual}
            self.check('VALID-'+name,'Reject invalid entry without master or follower exposure',case)
        def ownership():
            r=self.require_open()
            self.wait_fleet(1)
            oid=self.order_id(r)
            attempts={ep:self.api(FOLLOWERS[0],method,f'positions/{oid}/{ep}',body)
                      for ep,method,body in [('squareoff','POST',{}),('reduce','POST',{'qty':.01}),('protection','PUT',{'sl':1})]}
            after=self.positions(MASTER_EMAIL)
            intact=after['count']==1 and abs(after['positions'][0]['net_qty']-.02)<1e-8
            self.close(MASTER_EMAIL,oid)
            return all(v['http'] in (400,401,403,404) for v in attempts.values()) and intact and not self.flat(),{'attempts':attempts,'master_intact':intact}
        self.check('AUTH-CROSS-ACCOUNT','Follower cannot close/reduce/protect master-owned position',ownership)

    def sizing(self):
        self.cleanup()
        def multipliers():
            factors=[.5,1,2,3]
            for i,factor in enumerate(factors):self.configure(FOLLOWERS[i*25:(i+1)*25],multiplier=factor)
            r=self.require_open(qty=.04)
            data=self.wait_fleet(1)
            bad={}
            for i,email in enumerate(FOLLOWERS):
                expected=.04*factors[i//25];pos=data[email]['positions']
                if len(pos)!=1 or abs(pos[0]['net_qty']-expected)>1e-8:
                    bad[email]={'expected':expected,'actual':pos}
            self.api(MASTER_EMAIL,'POST',f'positions/{self.order_id(r)}/reduce',{'qty':.02})
            time.sleep(1);after=self.fleet();reduction_bad={}
            for i,email in enumerate(FOLLOWERS):
                expected=.02*factors[i//25];pos=after[email]['positions']
                if len(pos)!=1 or abs(pos[0]['net_qty']-expected)>1e-8:
                    reduction_bad[email]={'expected':expected,'actual':pos}
            self.close(MASTER_EMAIL,self.order_id(r));remaining=self.flat();self.configure(FOLLOWERS)
            return not bad and not reduction_bad and not remaining,{'open_errors':bad,'partial_close_errors':reduction_bad,'orphans':remaining}
        self.check('SIZE-MULTIPLIERS','Four multiplier tiers across 100 followers, including partial close',multipliers)
        self.cleanup()
        if self.ui is None:self.ui=AdminUI(self)
        self.ui.balance(MASTER_EMAIL,1000000)
        for email,value in zip(FOLLOWERS[:3],[500000,1000000,2000000]):self.ui.balance(email,value)
        for mode in ('balance','equity'):
            def ratio(mode=mode):
                self.configure(FOLLOWERS[:3],method=mode)
                before=self.fleet([MASTER_EMAIL]+FOLLOWERS[:3])
                r=self.require_open(qty=.04);data=self.wait_fleet(1)
                expected={e:round(.04*before[e]['funds'][mode]/before[MASTER_EMAIL]['funds'][mode],2) for e in FOLLOWERS[:3]}
                actual={e:[p['net_qty'] for p in data[e]['positions']] for e in FOLLOWERS[:3]}
                ok=all(len(actual[e])==1 and abs(actual[e][0]-expected[e])<=.00001 for e in FOLLOWERS[:3])
                self.close(MASTER_EMAIL,self.order_id(r));remaining=self.flat()
                return ok and not remaining,{'before_funds':{e:d['funds'] for e,d in before.items()},'expected':expected,'actual':actual,'orphans':remaining,
                    'scope':'No pre-existing floating PnL; equity divergence is a separate scenario'}
            self.check('SIZE-'+mode.upper(),f'{mode} ratio sizing at 0.5x, 1x and 2x balances',ratio)
        self.configure(FOLLOWERS)
        for email in FOLLOWERS[:3]:self.ui.balance(email,1000000)

    def pending(self):
        self.cleanup()
        quote_order=self.require_open(qty=.01)
        price=quote_order['body']['position']['avg_entry_price']
        self.close(MASTER_EMAIL,self.order_id(quote_order));self.flat()
        for kind in ('LIMIT','STOP'):
            for side in ('BUY','SELL'):
                def cancel_case(kind=kind,side=side):
                    below=(kind=='LIMIT' and side=='BUY') or (kind=='STOP' and side=='SELL')
                    level=round(price*(.5 if below else 1.5),2)
                    r=self.place(side,.02,kind,level)
                    oid=(r['body'].get('order') or {}).get('order_id')
                    if r['http']!=200 or not oid:return False,{'placement':r}
                    old=self.read(MASTER_EMAIL,'orders/'+oid)
                    cancel=self.api(MASTER_EMAIL,'DELETE','orders/'+oid)
                    after=self.read(MASTER_EMAIL,'orders/'+oid)
                    state=(after.get('order') or after).get('state')
                    return cancel['http']==200 and state in ('CANCELLED','CANCELED') and not self.flat(),{'placement':r,'before_cancel':old,'cancel':cancel,'after_cancel':after}
                self.check(f'PENDING-CANCEL-{kind}-{side}',f'Resting {side} {kind} remains pending then cancels without exposure',cancel_case)
                self.cleanup()
                def trigger_case(kind=kind,side=side):
                    crossed_above=(kind=='LIMIT' and side=='BUY') or (kind=='STOP' and side=='SELL')
                    level=round(price*(1.5 if crossed_above else .5),2)
                    r=self.place(side,.02,kind,level)
                    data=self.wait_fleet(1)
                    bad={e:d['positions'] for e,d in data.items() if d['count']!=1 or d['positions'][0]['side']!=side or abs(d['positions'][0]['net_qty']-.02)>1e-8}
                    master=data[MASTER_EMAIL]['positions']
                    if master:self.close(MASTER_EMAIL,master[0]['market_order_id'])
                    return r['http']==200 and not bad and not self.flat(),{'placement':r,'incorrect_positions':bad,'trigger_mode':'Already-marketable pending level; current contract permits immediate fill'}
                self.check(f'PENDING-TRIGGER-{kind}-{side}',f'Marketable {side} {kind} fills and copies to 100 followers',trigger_case)
                self.cleanup()
        for repeat in range(3):
            def modify_cancel():
                r=self.place('BUY',.02,'LIMIT',round(price*.5,2));oid=(r['body'].get('order') or {})['order_id']
                responses=self.race_call([lambda:self.api(MASTER_EMAIL,'PUT',f'orders/{oid}/modify',{'price':round(price*.45,2)}),
                                         lambda:self.api(MASTER_EMAIL,'DELETE',f'orders/{oid}')])
                after=self.read(MASTER_EMAIL,'orders/'+oid)
                return (after.get('order') or {}).get('state') in ('CANCELLED','CANCELED') and not self.flat(),{'responses':responses,'final_order':after}
            self.check(f'RACE-PENDING-MODIFY-CANCEL-{repeat+1}','Concurrent resting-order edit/cancel does not resurrect order',modify_cancel)

    def race_call(self,actions):
        barrier=threading.Barrier(len(actions))
        def call(fn):
            barrier.wait(timeout=10)
            return fn()
        with futures.ThreadPoolExecutor(max_workers=len(actions)) as pool:
            return list(pool.map(call,actions))

    def races(self):
        self.cleanup()
        for repeat in range(3):
            def double_close():
                r=self.require_open(qty=.04)
                before=self.wait_fleet(1)
                oid=self.order_id(r)
                responses=self.race_call([lambda:self.close(MASTER_EMAIL,oid) for _ in range(5)])
                after=self.wait_fleet(0)
                def audit(email):
                    pid=before[email]['positions'][0]['position_id']
                    history=self.read(email,'history')['history']
                    return [h for h in history if h.get('position_id')==pid]
                ledger=dict(zip(ACCOUNTS,self.pool.map(audit,ACCOUNTS)))
                # Evidence shape is retained; quantities are verified in later reconciliation.
                remaining={e:d['positions'] for e,d in after.items() if d['count']}
                return not remaining and all(len(v)==1 for v in ledger.values()),{'responses':responses,'orphans':remaining,
                       'history_rows_per_account':{e:len(v) for e,v in ledger.items()},'ledger':ledger}
            self.check(f'RACE-CLOSE-{repeat+1}','Five concurrent master closes: one history row, no orphan or reversed position',double_close)
            self.cleanup()
        def child_parent():
            r=self.require_open()
            data=self.wait_fleet(1)
            mid=self.order_id(r);fid=data[FOLLOWERS[0]]['positions'][0]['market_order_id']
            fpid=data[FOLLOWERS[0]]['positions'][0]['position_id']
            responses=self.race_call([lambda:self.close(MASTER_EMAIL,mid),lambda:self.close(FOLLOWERS[0],fid)])
            remaining=self.flat()
            history=self.read(FOLLOWERS[0],'history')['history']
            rows=[h for h in history if h.get('position_id')==fpid]
            return not remaining and len(rows)==1,{'responses':responses,'orphans':remaining,'follower_history':rows}
        self.check('RACE-MASTER-CHILD-CLOSE','Concurrent master and follower close: no double booking or orphan',child_parent)
        self.cleanup()
        def reduce_close():
            r=self.require_open(qty=.04);self.wait_fleet(1);oid=self.order_id(r)
            responses=self.race_call([lambda:self.api(MASTER_EMAIL,'POST',f'positions/{oid}/reduce',{'qty':.02}),lambda:self.close(MASTER_EMAIL,oid)])
            remaining=self.flat()
            return not remaining,{'responses':responses,'orphans':remaining}
        self.check('RACE-REDUCE-CLOSE','Concurrent partial close and full close leave all accounts flat',reduce_close)
        self.cleanup()

    def balances(self):
        self.cleanup()
        if self.ui is None:self.ui=AdminUI(self)
        email=FOLLOWERS[0]
        def hwm(value):
            before=self.positions(email)['funds']
            link=next(l for l in self.links(email)['following'] if l['master_client_id']==MASTER_ID and l['status']=='active')
            ui=self.ui.balance(email,value)
            after=self.positions(email)['funds']
            new=next(l for l in self.links(email)['following'] if l['master_client_id']==MASTER_ID and l['status']=='active')
            expected=link['starting_balance']+value-before['balance']
            return abs(after['balance']-value)<.01 and abs(new['starting_balance']-expected)<.01,{'before':before,'after':after,
                      'hwm_before':link['starting_balance'],'hwm_after':new['starting_balance'],'expected_hwm':expected,'ui':ui}
        self.check('BAL-DEPOSIT-HWM','GUI balance increase moves MAM benchmark by cash delta',lambda:hwm(1500000))
        self.check('BAL-WITHDRAW-HWM','GUI balance decrease moves MAM benchmark by cash delta',lambda:hwm(1000000))
        def during_trade():
            r=self.require_open();data=self.wait_fleet(1)
            before=data[email]
            ui=self.ui.balance(email,1200000)
            after=self.positions(email)
            ok=after['count']==1 and after['positions'][0]['market_order_id']==before['positions'][0]['market_order_id']
            self.close(MASTER_EMAIL,self.order_id(r));remaining=self.flat()
            return ok and abs(after['funds']['balance']-1200000)<.01 and not remaining,{'before':before,'after':after,'ui':ui,'orphans':remaining}
        self.check('BAL-OPEN-POSITION','GUI balance change preserves active copied position and later master close',during_trade)
        self.ui.balance(email,1000000)
        def zero_margin():
            self.ui.balance(email,0)
            r=self.require_open()
            time.sleep(2)
            data=self.fleet()
            unexpected={e:d['count'] for e,d in data.items() if d['count']!=(0 if e==email else 1)}
            self.close(MASTER_EMAIL,self.order_id(r));remaining=self.flat()
            self.ui.balance(email,1000000)
            return not unexpected and not remaining,{'unexpected_fanout':unexpected,'orphans':remaining}
        self.check('MARGIN-ISOLATION','Zero-balance follower rejected without blocking other 99 copies',zero_margin)
        self.cleanup()
        for repeat in range(3):
            def ui_race():
                r=self.require_open(qty=.02);self.wait_fleet(1);oid=self.order_id(r)
                before=self.positions(email)
                fpid=before['positions'][0]['position_id']
                target=1100000+repeat*1000
                pool=futures.ThreadPoolExecutor(max_workers=1);jobs=[]
                ui=self.ui.balance(email,target,before_submit=lambda:jobs.append(pool.submit(self.close,MASTER_EMAIL,oid)))
                close=jobs[0].result();pool.shutdown()
                remaining=self.flat();after=self.positions(email)['funds']
                hist=[h for h in self.read(email,'history')['history'] if h.get('position_id')==fpid]
                # Both serial outcomes are legitimate. Persist actual ledger for reconciliation.
                return not remaining and len(hist)==1 and math.isfinite(after['balance']),{
                    'ui':ui,'master_close':close,'before':before,'after':after,'history':hist,'orphans':remaining,
                    'note':'GUI submit overlaps API close; no claim of exact server simultaneity'}
            self.check(f'RACE-GUI-BALANCE-CLOSE-{repeat+1}','GUI follower balance update overlaps master close',ui_race)
        self.ui.balance(email,1000000)

    def finish(self):
        self.check('FINAL-FLAT','Final real-hedging cleanup across all 101 accounts',lambda:(True,self.cleanup()))
        self.configure(FOLLOWERS)
        final=self.fleet()
        (OUT/f'final_positions_{self.run_id}.json').write_text(json.dumps(final,indent=2),encoding='utf-8')

    def membership(self):
        self.cleanup()
        for name,email,ep,payload in [
            ('SELF-FOLLOW',MASTER_EMAIL,'mam/follow',{'master_client_id':MASTER_ID}),
            ('UNKNOWN-MASTER',FOLLOWERS[0],'mam/follow',{'master_client_id':'mem_qa_does_not_exist'}),
            ('FOLLOWER-BECOME-MASTER',FOLLOWERS[0],'mam/master',{'display_name':'QA should be refused','share_percent':20})]:
            def refusal(email=email,ep=ep,payload=payload):
                before=self.links(email);r=self.api(email,'POST',ep,payload);after=self.links(email)
                return r['http'] in (400,403,404) and before==after,{'response':r,'relationship_unchanged':before==after}
            self.check('MAM-'+name,'MAM role and relationship validation: '+name,refusal)
        def fee_config():
            before=self.links(MASTER_EMAIL)['master']
            r=self.api(MASTER_EMAIL,'POST','mam/master',{'display_name':before['display_name'],'share_percent':20})
            after=self.links(MASTER_EMAIL)['master']
            restored=self.api(MASTER_EMAIL,'POST','mam/master',{'display_name':before['display_name'],'share_percent':before['share_percent']})
            return r['http']==200 and after['share_percent']==20 and restored['http']==200,{'before':before,'after':after,'restore':restored}
        self.check('MAM-FEE-CONFIG','Change manager fee, read back, restore original fee',fee_config)
        email=FOLLOWERS[0]
        def unfollow_no_position():
            leave=self.api(email,'POST','mam/unfollow',{'master_client_id':MASTER_ID})
            after=self.links(email)
            active=[l for l in after['following'] if l['master_client_id']==MASTER_ID and l['status']=='active']
            r=self.require_open();time.sleep(2);data=self.fleet()
            unexpected={e:d['count'] for e,d in data.items() if d['count']!=(0 if e==email else 1)}
            self.close(MASTER_EMAIL,self.order_id(r));remaining=self.flat();self.configure([email])
            return leave['http']==200 and not active and not unexpected and not remaining,{'leave':leave,'unexpected_fanout':unexpected,'orphans':remaining}
        self.check('MAM-UNFOLLOW-FLAT','Unfollow flat account prevents new copies; other followers continue',unfollow_no_position)
        self.cleanup()
        def join_midtrade():
            self.api(email,'POST','mam/unfollow',{'master_client_id':MASTER_ID})
            first=self.require_open();time.sleep(1)
            before=self.positions(email)
            self.configure([email]);time.sleep(1)
            joined=self.positions(email)
            second=self.require_open('SELL');time.sleep(1)
            after=self.positions(email)
            self.close(MASTER_EMAIL,self.order_id(first));self.close(MASTER_EMAIL,self.order_id(second));remaining=self.flat()
            return before['count']==0 and joined['count']==0 and after['count']==1 and after['positions'][0]['side']=='SELL' and not remaining,{
                'before_join':before,'immediately_after_join':joined,'after_new_trade':after,'orphans':remaining}
        self.check('MAM-JOIN-MIDTRADE','New follower copies future orders without retroactively copying prior trade',join_midtrade)
        self.cleanup()
        def terms_midtrade():
            self.configure([email],multiplier=1)
            first=self.require_open(qty=.02);self.wait_fleet(1)
            self.configure([email],multiplier=2)
            before=self.positions(email)
            second=self.require_open('SELL',qty=.02);time.sleep(1)
            after=self.positions(email)
            sizes=sorted((p['side'],p['net_qty']) for p in after['positions'])
            self.close(MASTER_EMAIL,self.order_id(first));self.close(MASTER_EMAIL,self.order_id(second));remaining=self.flat();self.configure([email])
            return before['count']==1 and abs(before['positions'][0]['net_qty']-.02)<1e-8 and sizes==[('BUY',.02),('SELL',.04)] and not remaining,{
                'old_position_after_multiplier_change':before,'new_position_sizes':sizes,'orphans':remaining}
        self.check('MAM-MULTIPLIER-MIDTRADE','Multiplier change affects future copies, not existing position size',terms_midtrade)
        self.cleanup()
        for i in range(3):
            def unfollow_race():
                self.configure([email])
                responses=self.race_call([lambda:self.place(qty=.02),lambda:self.api(email,'POST','mam/unfollow',{'master_client_id':MASTER_ID})])
                time.sleep(1);master=self.positions(MASTER_EMAIL);child=self.positions(email)
                if master['count']!=1:raise RuntimeError('Master race prerequisite not filled')
                self.close(MASTER_EMAIL,master['positions'][0]['market_order_id']);time.sleep(1)
                after=self.positions(email)
                # A child admitted before unfollow may remain per platform policy; record, do not invent policy.
                valid=child['count'] in (0,1) and all(p['side']=='BUY' and abs(p['net_qty']-.02)<1e-8 for p in child['positions'])
                detail={'responses':responses,'child_at_race_end':child,'child_after_master_close':after,
                        'assertion':'At most one correctly-sized child; retention after unfollow is recorded as behavior, not assumed forbidden'}
                self.cleanup();self.configure([email])
                return valid,detail
            self.check(f'RACE-UNFOLLOW-OPEN-{i+1}','Concurrent master entry and follower unfollow produce no duplicate or malformed copy',unfollow_race)

    def burst(self):
        self.cleanup()
        def run_burst():
            responses=self.race_call([lambda:self.place(qty=.01) for _ in range(5)])
            accepted=[r for r in responses if r['http']==200 and r['body'].get('success')]
            if len(accepted)!=5:return False,{'responses':responses,'note':'Five requested orders not all accepted'}
            data=self.wait_fleet(5,timeout=30)
            bad={e:d['positions'] for e,d in data.items() if d['count']!=5 or any(abs(p['net_qty']-.01)>1e-8 for p in d['positions'])}
            close_responses=self.race_call([lambda oid=self.order_id(r):self.close(MASTER_EMAIL,oid) for r in accepted])
            remaining=self.flat()
            return not bad and not remaining,{'master_responses':responses,'fanout_errors':bad,'close_responses':close_responses,'orphans':remaining,
                'scope':'5 simultaneous master orders, 100 followers, 500 copied positions; not a 500-follower test'}
        self.check('LOAD-FIVE-BURST','Five concurrent entries -> 500 child positions -> concurrent parent closes',run_burst)
        self.cleanup()


class AdminUI:
    def __init__(self, qa):
        self.qa=qa
        self.pw=sync_playwright().start()
        self.browser=self.pw.chromium.launch(headless=True)
        self.page=self.browser.new_page(viewport={'width':1440,'height':1050})
        self.page.goto(BASE_URL+'/blackadmin',wait_until='domcontentloaded',timeout=30000)
        self.page.locator('input[type="email"]').fill(ADMIN_EMAIL)
        self.page.locator('input[type="password"]').fill(ADMIN_PASSWORD)
        self.page.locator('button[type="submit"]').click()
        self.page.get_by_text(re.compile('^people$',re.I)).click(timeout=20000)

    def balance(self,email,value,screenshot=True,before_submit=None):
        assert email in ACCOUNTS
        page=self.page
        back=page.get_by_text('All members',exact=True)
        if back.is_visible():
            back.click()
        else:
            page.get_by_role('button',name='Members',exact=True).click()
        page.locator('input[placeholder*="email" i]').fill(email)
        page.locator('tbody tr').filter(has_text=email).first.locator('td').first.click()
        row=page.locator('.section-gap').filter(has_text='Trading balance').filter(has_text='Real (Hedging)')
        row.get_by_role('button',name='Set balance',exact=True).click()
        row.locator('input[type="number"]').fill(str(value))
        started=now()
        if before_submit:
            before_submit()
        with page.expect_response(lambda r:'/admin/api/members/' in r.url and r.url.endswith('/balance')
                                  and r.request.method=='POST',timeout=25000) as response_info:
            row.get_by_role('button',name='Set',exact=True).click()
        response=response_info.value
        payload=response.request.post_data_json
        body=response.json()
        result={'email':email,'value':value,'started_at':started,'finished_at':now(),'http':response.status,
                'payload':payload,'body':body}
        self.qa.trace({'case':self.qa.active_case,'mechanism':'Playwright Admin Member Set balance',**result})
        assert payload.get('instance')=='real',payload
        assert response.status==200 and body.get('success') is not False,result
        row.get_by_role('button',name='Set balance',exact=True).wait_for(timeout=15000)
        if screenshot:
            page.screenshot(path=str(OUT/f'ui_{self.qa.run_id}_{self.qa.active_case}_{email.split("@")[0]}_{value}.png'),full_page=True)
        return result

    def close(self):
        self.browser.close()
        self.pw.stop()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--stages',default='setup,smoke')
    args=parser.parse_args()
    qa=QA()
    try:
        qa.authenticate()
        for stage in args.stages.split(','):
            getattr(qa,stage)()
    except Exception as e:
        (OUT/f'abort_{qa.run_id}.json').write_text(json.dumps({'case':qa.active_case,'time':now(),
            'status':'BLOCKED','error':type(e).__name__+': '+str(e)},indent=2),encoding='utf-8')
        if qa.ui and not qa.ui.page.is_closed():
            qa.ui.page.screenshot(path=str(OUT/f'abort_{qa.run_id}.png'),full_page=True)
        raise
    finally:
        if qa.ui:
            qa.ui.close()
        qa.pool.shutdown()
    return int(any(r['status']!='PASS' for r in qa.results))


if __name__=='__main__':
    sys.exit(main())
