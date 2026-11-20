"""Additional live assertions grounded in observed response schemas."""
import argparse
import concurrent.futures as futures
import hashlib
import gzip
import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
from qa_mam_live import QA, AdminUI, OUT, SYMBOL, MASTER_EMAIL, MASTER_ID, FOLLOWERS, ACCOUNTS, now


class DeepQA(QA):
    def __init__(self):
        super().__init__()
        self.trace_path=self.trace_path.with_suffix('.jsonl.gz')

    def trace(self,data):
        with self.lock:
            with gzip.open(self.trace_path,'at',encoding='utf-8',compresslevel=3) as f:
                f.write(json.dumps(data,ensure_ascii=True)+'\n')

    def quantization(self):
        self.cleanup()
        email=FOLLOWERS[0]
        for qty,mult,expected in [(.01,.25,.01),(.03,.5,.02),(.01,1.5,.02),(.01,2.75,.03)]:
            def case(qty=qty,mult=mult,expected=expected):
                self.configure([email],multiplier=mult)
                r=self.require_open(qty=qty);time.sleep(1)
                data=self.wait_fleet(1)
                child=data[email]
                other_errors={e:d for e,d in data.items() if e!=email and
                              (d['count']!=1 or abs(d['positions'][0]['net_qty']-qty)>1e-8)}
                invalid=[p for p in child['positions'] if p['net_qty']<.01-1e-9 or abs(p['net_qty']/.01-round(p['net_qty']/.01))>1e-7]
                self.close(MASTER_EMAIL,self.order_id(r));remaining=self.flat();self.configure([email])
                exact=child['count']==1 and abs(child['positions'][0]['net_qty']-expected)<1e-8
                return exact and not other_errors and not invalid and not remaining,{'master_qty':qty,'multiplier':mult,'unrounded_product':qty*mult,
                    'child_positions':child['positions'],'invalid_entry_quantities':invalid,'orphans':remaining,
                    'expected_child_quantity':expected,'other_account_errors':other_errors,
                    'oracle':'Regression of observed .01 minimum and nearest-step rounding; exactly one child required, no missing-copy pass'}
            self.check(f'SIZE-LOT-RULE-{qty}-{mult}','Copied new entry respects BLACK BTCUSD lot minimum and step',case)
        self.cleanup()

    def final_normalize(self):
        self.cleanup()
        self.configure(FOLLOWERS)
        if self.ui is None:self.ui=AdminUI(self)
        def reset():
            changes=[]
            for i,email in enumerate(ACCOUNTS):
                changes.append(self.ui.balance(email,1000000,screenshot=i in (0,1,100)))
                if i%10==0:print(f'Final GUI balance reset: {i+1}/101',flush=True)
            data=self.fleet()
            links=dict(zip(ACCOUNTS,self.pool.map(self.links,ACCOUNTS)))
            def active(email):return [o for o in self.read(email,'orders')['orders'] if o.get('state') in ('PENDING','OPEN','NEW')]
            pending=dict(zip(ACCOUNTS,self.pool.map(active,ACCOUNTS)))
            errors={e:d for e,d in data.items() if d['count']!=0 or abs(d['funds']['balance']-1000000)>.01 or pending[e]}
            link_errors={}
            for email in FOLLOWERS:
                target=[r for r in links[email]['following'] if r['master_client_id']==MASTER_ID and r['status']=='active']
                if len(target)!=1 or target[0].get('method')!='multiplier' or target[0].get('multiplier')!=1:
                    link_errors[email]=target
            snapshot={'time':now(),'positions':data,'relationships':links,'working_orders':pending,'gui_changes':changes}
            (OUT/'final_account_state.json').write_text(json.dumps(snapshot,indent=2),encoding='utf-8')
            return not errors and not link_errors,{'accounts_verified':len(data),'balance_each':1000000,'positions_and_balance_errors':errors,
                'relationship_errors':link_errors,'working_order_count':sum(map(len,pending.values())),
                'snapshot':'final_account_state.json','master_configuration':links[MASTER_EMAIL].get('master')}
        self.check('FINAL-ACCOUNT-STATE','GUI reset and readback: 101 balances, flat inventory, no pending orders and 100 active multiplier-one links',reset)


    def pending_fanout(self):
        self.cleanup()
        seed=self.require_open(qty=.01);price=seed['body']['position']['avg_entry_price']
        self.close(MASTER_EMAIL,self.order_id(seed));self.flat()
        for kind,side in [('LIMIT','BUY'),('STOP','SELL')]:
            def case(kind=kind,side=side):
                r=self.place(side,.02,kind,round(price*.5,2))
                if r['http']!=200:raise RuntimeError('Pending prerequisite failed: '+str(r))
                order=r['body']['order'];group=order['group_id'];time.sleep(1)
                def matching(email):return [o for o in self.read(email,'orders')['orders'] if o.get('group_id')==group]
                before=dict(zip(ACCOUNTS,self.pool.map(matching,ACCOUNTS)))
                errors={e:orders for e,orders in before.items() if len(orders)!=1 or orders[0]['state']!='PENDING'
                        or orders[0]['type']!=kind or abs(orders[0]['requested_qty']-.02)>1e-8}
                cancel=self.api(MASTER_EMAIL,'DELETE','orders/'+order['order_id'])
                time.sleep(.5);after=dict(zip(ACCOUNTS,self.pool.map(matching,ACCOUNTS)))
                still_working={e:orders for e,orders in after.items() if any(o.get('state') in ['PENDING','OPEN','NEW'] for o in orders)}
                flat=self.flat()
                return not errors and cancel['http']==200 and not still_working and not flat,{
                    'placement':r,'before':before,'after':after,'missing_or_wrong_pending_children':errors,'still_working':still_working,'positions':flat}
            self.check(f'PENDING-100-FANOUT-{kind}',f'Pending {kind} tickets appear on all followers and cancel with master',case)
            self.cleanup()

    def margin_races(self):
        self.cleanup()
        if self.ui is None:self.ui=AdminUI(self)
        email=FOLLOWERS[0]
        self.configure([email])
        for i in range(3):
            def case():
                self.ui.balance(email,2000)
                responses=self.race_call([lambda:self.place(qty=.02),lambda:self.place(qty=.02)])
                if any(r['http']!=200 for r in responses):raise RuntimeError('Master prerequisites failed: '+str(responses))
                time.sleep(1);data=self.fleet();child=data[email]
                # Each .02 BLACK BTCUSD entry needs approximately 1,240 margin on this group.
                # Two entries cannot both fit in 2,000 at the observed price/margin terms.
                errors={e:d['count'] for e,d in data.items() if e!=email and d['count']!=2}
                ok=child['count']==1 and child['funds']['free_margin']>=-.01 and not errors
                for r in responses:self.close(MASTER_EMAIL,self.order_id(r))
                remaining=self.flat()
                return ok and not remaining,{'master_responses':responses,'limited_follower':child,'other_account_errors':errors,'orphans':remaining}
            self.check(f'RACE-MARGIN-RESERVATION-{i+1}','Two master entries compete for one follower margin allocation',case)
        self.ui.balance(email,1000000)
        self.cleanup()

    def more_races(self):
        self.cleanup()
        for i in range(3):
            def reductions():
                r=self.require_open(qty=.04);before=self.wait_fleet(1);oid=self.order_id(r)
                responses=self.race_call([lambda:self.api(MASTER_EMAIL,'POST',f'positions/{oid}/reduce',{'qty':.01}) for _ in range(5)])
                remaining=self.flat()
                def history(email):
                    pid=before[email]['positions'][0]['position_id']
                    return [h for h in self.read(email,'history')['history'] if h.get('position_id')==pid]
                ledger=dict(zip(ACCOUNTS,self.pool.map(history,ACCOUNTS)))
                bad={e:h for e,h in ledger.items() if not h or abs(sum(x['qty'] for x in h)-.04)>1e-8}
                return not remaining and not bad,{'responses':responses,'quantity_errors':bad,'orphans':remaining,'ledger':ledger}
            self.check(f'RACE-MULTI-REDUCE-{i+1}','Five reductions cannot close more than original .04 quantity',reductions)
            self.cleanup()
        def separate_fields():
            r=self.require_open();self.wait_fleet(1);oid=self.order_id(r);price=r['body']['position']['avg_entry_price']
            responses=self.race_call([lambda:self.api(MASTER_EMAIL,'PUT',f'positions/{oid}/protection',{'sl':price-10000}),
                                     lambda:self.api(MASTER_EMAIL,'PUT',f'positions/{oid}/protection',{'tp':price+10000})])
            time.sleep(.5);data=self.fleet()
            def brackets(email):
                mid=data[email]['positions'][0]['market_order_id']
                return [o for o in self.read(email,'orders')['orders'] if o.get('market_order_id')==mid and o.get('state')=='PENDING']
            all_orders=dict(zip(ACCOUNTS,self.pool.map(brackets,ACCOUNTS)))
            bad={e:v for e,v in all_orders.items() if {o['type'] for o in v}!={'SL','TP'} or len(v)!=2}
            self.close(MASTER_EMAIL,oid);remaining=self.flat()
            return all(r['http']==200 for r in responses) and not bad and not remaining,{'responses':responses,'lost_updates':bad,'orphans':remaining}
        self.check('RACE-INDEPENDENT-SL-TP','Concurrent independent bracket edits preserve both supplied fields',separate_fields)
        self.cleanup()

    def manual_follower(self):
        self.cleanup()
        def case():
            r=self.require_open();data=self.wait_fleet(1)
            independent=self.api(FOLLOWERS[0],'POST','orders',{'symbol':SYMBOL,'side':'SELL','qty':.02,'type':'MARKET','tag':'QA_INDEPENDENT'})
            if independent['http']!=200:
                self.close(MASTER_EMAIL,self.order_id(r));self.flat()
                raise RuntimeError('Independent follower entries refused; policy requires clarification: '+str(independent))
            self.close(MASTER_EMAIL,self.order_id(r));time.sleep(1);after=self.fleet()
            errors={e:d['positions'] for e,d in after.items() if d['count']!=(1 if e==FOLLOWERS[0] else 0)}
            child=after[FOLLOWERS[0]]['positions']
            correct=len(child)==1 and child[0]['side']=='SELL' and child[0]['market_order_id']==self.order_id(independent)
            if child:self.close(FOLLOWERS[0],child[0]['market_order_id'])
            return correct and not errors and not self.flat(),{'independent_order':independent,'remaining_follower_position':child,'unexpected_accounts':errors}
        self.check('ISOLATE-MANUAL-FOLLOWER','Master close preserves follower independent opposite-side trade',case)
        self.cleanup()


    def gui_matrix(self):
        self.cleanup()
        if self.ui is None:self.ui=AdminUI(self)
        self.configure(FOLLOWERS)
        self.ui.balance(MASTER_EMAIL,1000000)
        self.ui.balance(FOLLOWERS[0],1000000)
        def master_cash():
            r=self.require_open();before=self.wait_fleet(1)
            ui=self.ui.balance(MASTER_EMAIL,1500000)
            after=self.fleet()
            changed={e:{'before':before[e],'after':after[e]} for e in FOLLOWERS
                     if abs(before[e]['funds']['balance']-after[e]['funds']['balance'])>.01
                     or [p['position_id'] for p in before[e]['positions']]!=[p['position_id'] for p in after[e]['positions']]}
            self.close(MASTER_EMAIL,self.order_id(r));remaining=self.flat()
            return not changed and not remaining,{'ui':ui,'unexpected_follower_changes':changed,'orphans':remaining}
        self.check('GUI-MASTER-CASH-ISOLATION','Admin master cash adjustment does not transfer cash or resize follower trades',master_cash)
        self.ui.balance(MASTER_EMAIL,1000000)
        email=FOLLOWERS[0]
        def dynamic_balance():
            self.configure([email],method='balance')
            self.ui.balance(email,1000000)
            first=self.require_open(qty=.02);self.wait_fleet(1)
            old=self.positions(email)['positions'][0]
            self.ui.balance(email,2000000)
            second=self.require_open('SELL',qty=.02);time.sleep(1)
            before_close=self.positions(email)
            sizes=sorted((p['side'],p['net_qty']) for p in before_close['positions'])
            self.close(MASTER_EMAIL,self.order_id(first));time.sleep(1)
            after_close=self.positions(email)
            correct=after_close['count']==1 and after_close['positions'][0]['side']=='SELL' and abs(after_close['positions'][0]['net_qty']-.04)<1e-8
            self.close(MASTER_EMAIL,self.order_id(second));remaining=self.flat();self.configure([email]);self.ui.balance(email,1000000)
            return sizes==[('BUY',.02),('SELL',.04)] and correct and not remaining,{'old_position':old,'positions_after_cash_change':before_close,
                'after_old_master_close':after_close,'orphans':remaining}
        self.check('GUI-BALANCE-NEXT-ORDER','Follower cash update changes future ratio size without resizing or misclosing existing trade',dynamic_balance)
        for i in range(3):
            def opening_race():
                self.configure([email],method='balance');self.ui.balance(email,1000000)
                with futures.ThreadPoolExecutor(max_workers=1) as pool:
                    jobs=[]
                    ui=self.ui.balance(email,2000000,before_submit=lambda:jobs.append(pool.submit(self.place,qty=.02)))
                    opened=jobs[0].result()
                if opened['http']!=200:raise RuntimeError('Master entry failed: '+str(opened))
                time.sleep(1);data=self.fleet();pos=data[email]['positions']
                valid=len(pos)==1 and any(abs(pos[0]['net_qty']-q)<1e-8 for q in [.02,.04])
                others={e:d['count'] for e,d in data.items() if e!=email and d['count']!=1}
                self.close(MASTER_EMAIL,self.order_id(opened));remaining=self.flat();self.configure([email]);self.ui.balance(email,1000000)
                return valid and not others and not remaining,{'ui':ui,'master_order':opened,'follower_position':pos,'other_errors':others,'orphans':remaining,
                    'allowed_outcomes':'One child sized to the old or new balance; neither timing order assumed'}
            self.check(f'RACE-GUI-BALANCE-ENTRY-{i+1}','GUI follower cash change races master entry under balance allocation',opening_race)
        self.cleanup()

    def fee_live_larger_fixture(self):
        self.fee_live(qty=2)

    def fee_boundary_reproduce(self):
        self.cleanup()
        if self.ui is None:self.ui=AdminUI(self)
        email=FOLLOWERS[0]
        self.api(email,'POST','mam/unfollow',{'master_client_id':MASTER_ID})
        self.ui.balance(email,1000000)
        self.configure([email])
        def winner(expected_above):
            before=self.positions(email)['funds']
            link=next(x for x in self.links(email)['following'] if x['master_client_id']==MASTER_ID and x['status']=='active')
            if (before['balance']>link['starting_balance'])!=expected_above:
                raise RuntimeError('Required pre-close HWM fixture is not established')
            buysell=[self.require_open('BUY',qty=2),self.require_open('SELL',qty=2)]
            groups={r['body']['position']['group_id']:r for r in buysell}
            deadline=time.monotonic()+50
            chosen=None
            while time.monotonic()<deadline:
                eligible=[p for p in self.positions(email)['positions'] if p['group_id'] in groups and p['unrealized_pnl']>15]
                if eligible:
                    chosen=max(eligible,key=lambda p:p['unrealized_pnl']);break
                time.sleep(1)
            if chosen is None:raise RuntimeError('No profitable hedged-side fixture within observation window')
            result=self.close(MASTER_EMAIL,self.order_id(groups[chosen['group_id']]))
            time.sleep(.5)
            history=[h for h in self.read(email,'history')['history'] if h.get('position_id')==chosen['position_id']]
            ids={h['history_id'] for h in history}
            shares=[s for s in self.read(email,'mam/shares')['shares'] if s.get('trade_id') in ids and s.get('instance')=='real']
            after=self.positions(email)['funds']
            if len(history)!=1 or history[0]['realized_pnl']<=6 or result['http']!=200:
                raise RuntimeError('Profitable close prerequisite was not met')
            expected_share=round(history[0]['realized_pnl']*link['share_percent']/100,2) if expected_above else 0
            terms=self.read(email,'account')['account']['brokerage']
            if terms.get('mode')!='per_lot':raise RuntimeError('Brokerage oracle requires per-lot terms')
            commission=min(max(float(terms.get('min',0)),float(terms.get('rates',{}).get('default',0))*history[0]['qty']),float(terms.get('max') or math.inf))
            expected_balance=before['balance']+history[0]['realized_pnl']-commission-expected_share
            correct=(len(shares)==1 and shares[0]['above_hwm']==expected_above
                     and abs(shares[0]['master_share']-expected_share)<.011
                     and abs(shares[0]['master_share']+shares[0]['follower_share']-round(shares[0]['order_pnl'],2))<.011
                     and abs(after['balance']-expected_balance)<.011)
            return correct,{'balance_before_entry':before,'balance_after_close':after,'relationship':link,
                'history':history,'shares':shares,'already_above_before_trade':expected_above,
                'expected_manager_share':expected_share,'expected_balance':expected_balance,'brokerage':commission,
                'assertion':'User-confirmed rule: first profit at benchmark is not shared; subsequent profitable close above benchmark pays configured percentage; balance and split reconcile'}
        self.check('FEE-HWM-POLICY-FIRST','Confirmed policy: first profitable benchmark crossing has zero manager share',lambda:winner(False))
        self.check('FEE-HWM-POLICY-ABOVE','Confirmed policy: later profit above benchmark shares 50 percent and reconciles balance',lambda:winner(True))
        self.cleanup()

    def fee_live(self,qty=.2):
        self.cleanup()
        if self.ui is None:self.ui=AdminUI(self)
        email=FOLLOWERS[0]
        self.configure([email])
        def profitable_trade():
            # Reset the relationship baseline through an actual end/rejoin, not by editing internal state.
            self.api(email,'POST','mam/unfollow',{'master_client_id':MASTER_ID})
            self.ui.balance(email,1000000)
            self.configure([email])
            initial=self.links(email)
            r=self.require_open(qty=qty);data=self.wait_fleet(1)
            pid=data[email]['positions'][0]['position_id']
            deadline=time.monotonic()+50
            reached=False
            while time.monotonic()<deadline:
                p=self.positions(email)['positions']
                if p and p[0]['unrealized_pnl']>10:
                    reached=True;break
                time.sleep(1)
            self.close(MASTER_EMAIL,self.order_id(r));self.flat()
            hist=[h for h in self.read(email,'history')['history'] if h.get('position_id')==pid]
            ids={h['history_id'] for h in hist}
            shares=[s for s in self.read(email,'mam/shares')['shares'] if s.get('trade_id') in ids and s.get('instance')=='real']
            if not reached or not hist or hist[0]['realized_pnl']<=6:
                raise RuntimeError('Live market did not provide required profitable-above-fees fixture; no fee claim made')
            return len(shares)==1 and shares[0]['master_share']==0 and shares[0]['above_hwm'] is False and abs(shares[0]['master_share']+shares[0]['follower_share']-round(shares[0]['order_pnl'],2))<=.011,{
                'initial_relationship':initial,'history':hist,'shares':shares,'assertion':'User-confirmed first-profitable-trade exemption; rounded split PnL conserved'}
        self.check('FEE-LIVE-PROFIT','Observe actual profitable close and corresponding manager/follower profit split',profitable_trade)
        self.cleanup()

    def protection_retest(self):
        self.cleanup()
        def test():
            r=self.require_open();self.wait_fleet(1);oid=self.order_id(r)
            price=r['body']['position']['avg_entry_price'];sl=price-10000;tp=price+10000
            edit=self.api(MASTER_EMAIL,'PUT',f'positions/{oid}/protection',{'sl':sl,'tp':tp})
            time.sleep(.5);data=self.fleet()
            def inspect(email):
                positions=data[email]['positions']
                if len(positions)!=1:return {'error':'Expected one position'}
                mid=positions[0]['market_order_id']
                brackets=[o for o in self.read(email,'orders')['orders'] if o.get('market_order_id')==mid and o.get('state')=='PENDING']
                return {'market_order_id':mid,'brackets':brackets}
            evidence=dict(zip(ACCOUNTS,self.pool.map(inspect,ACCOUNTS)))
            bad={}
            for email,row in evidence.items():
                brackets=row.get('brackets',[])
                if len(brackets)!=2 or {o['type'] for o in brackets}!={'SL','TP'} or any(abs(o.get('trigger_price',0)-(sl if o['type']=='SL' else tp))>.01 for o in brackets):
                    bad[email]=row
            remove=self.api(MASTER_EMAIL,'PUT',f'positions/{oid}/protection',{'sl':0,'tp':0})
            time.sleep(.5)
            def remaining(email):
                mid=evidence[email].get('market_order_id')
                return [o for o in self.read(email,'orders')['orders'] if o.get('market_order_id')==mid and o.get('state')=='PENDING']
            remnants={e:v for e,v in zip(ACCOUNTS,self.pool.map(remaining,ACCOUNTS)) if v}
            self.close(MASTER_EMAIL,oid)
            return edit['http']==200 and remove['http']==200 and not bad and not remnants and not self.flat(),{
                'supersedes':'LIFE-PROTECTION initial assertion used nonexistent parent_order_id; actual link field is market_order_id',
                'incorrect_brackets':bad,'remaining_brackets_after_removal':remnants,'bracket_evidence':evidence}
        self.check('LIFE-PROTECTION-RETEST','Set and remove SL/TP across all 101 accounts using actual linkage field',test)
        self.cleanup()

    def accounting(self):
        self.cleanup()
        def close_reconcile():
            before=self.fleet()
            r=self.require_open(qty=.02);open_state=self.wait_fleet(1)
            self.close(MASTER_EMAIL,self.order_id(r));self.flat();after=self.fleet()
            def inspect(email):
                pid=open_state[email]['positions'][0]['position_id']
                rows=[h for h in self.read(email,'history')['history'] if h.get('position_id')==pid]
                account=self.read(email,'account')['account']
                shares=self.read(email,'mam/shares')['shares'] if email!=MASTER_EMAIL else []
                ids={h['history_id'] for h in rows}
                related=[s for s in shares if s.get('trade_id') in ids and s.get('instance')=='real']
                return {'history':rows,'account_terms':account,'mam_shares':related}
            records=dict(zip(ACCOUNTS,self.pool.map(inspect,ACCOUNTS)))
            errors={};master_receipts=0
            for email,row in records.items():
                hist=row['history'];terms=row['account_terms']['brokerage']
                if len(hist)!=1:
                    errors[email]={'history_count':len(hist)};continue
                h=hist[0];pnl=h['realized_pnl'];qty=h['qty']
                expected_pnl=(h['exit_price']-h['entry_price'])*qty*(1 if h['side']=='BUY' else -1)
                # The tested Standard group exposes per_lot brokerage with default rate.
                if terms.get('mode')!='per_lot':raise RuntimeError('Unsupported brokerage oracle: '+str(terms))
                rate=terms.get('rates',{}).get('default',0)
                fee=max(float(terms.get('min',0)),float(rate)*qty)
                if terms.get('max',0)>0:fee=min(fee,float(terms['max']))
                share=sum(float(s['master_share']) for s in row['mam_shares'])
                master_receipts+=share
                row.update(expected_price_pnl=expected_pnl,brokerage=fee,share_paid=share,
                           actual_balance_delta=after[email]['funds']['balance']-before[email]['funds']['balance'])
                if abs(expected_pnl-pnl)>.01:errors[email]={'price_pnl_mismatch':row}
                funds=after[email]['funds']
                if abs(funds['used_margin'])>.01 or abs(funds['equity']-funds['balance'])>.01:
                    errors[email]={'nonflat_funds':funds}
            for email,row in records.items():
                if len(row['history'])!=1:continue
                expected=row['history'][0]['realized_pnl']-row['brokerage']-row['share_paid']+(master_receipts if email==MASTER_EMAIL else 0)
                row['expected_balance_delta']=expected
                if abs(row['actual_balance_delta']-expected)>.011:errors[email]={'balance_reconciliation':row}
            return not errors,{'errors':errors,'records':records,'master_fee_receipts':master_receipts,'before':before,'after':after}
        self.check('ACCOUNTING-101','Trade price PnL, brokerage, MAM fee transfers and balances reconcile across fleet',close_reconcile)
        self.cleanup()

    def balance_race_accounting(self):
        self.cleanup()
        if self.ui is None:self.ui=AdminUI(self)
        email=FOLLOWERS[0]
        for i in range(3):
            def race(i=i):
                r=self.require_open(qty=.02);opened=self.wait_fleet(1)
                pos=opened[email]['positions'][0];before=opened[email]['funds']
                link=next(l for l in self.links(email)['following'] if l['master_client_id']==MASTER_ID and l['status']=='active')
                target=1000000+i*10000
                with futures.ThreadPoolExecutor(max_workers=1) as pool:
                    jobs=[]
                    ui=self.ui.balance(email,target,before_submit=lambda:jobs.append(pool.submit(self.close,MASTER_EMAIL,self.order_id(r))))
                    close=jobs[0].result()
                self.flat();after=self.positions(email)['funds']
                newlink=next(l for l in self.links(email)['following'] if l['master_client_id']==MASTER_ID and l['status']=='active')
                hist=[h for h in self.read(email,'history')['history'] if h.get('position_id')==pos['position_id']]
                ids={h['history_id'] for h in hist}
                shares=[s for s in self.read(email,'mam/shares')['shares'] if s.get('trade_id') in ids and s.get('instance')=='real']
                terms=self.read(email,'account')['account']['brokerage']
                if terms.get('mode')!='per_lot':raise RuntimeError('Non-per-lot brokerage requires separate oracle')
                commission=sum(min(max(float(terms.get('min',0)),float(terms.get('rates',{}).get('default',0))*h['qty']),float(terms.get('max') or math.inf)) for h in hist)
                net=sum(h['realized_pnl'] for h in hist)-commission-sum(s['master_share'] for s in shares)
                # Admin response exposes committed cash delta, eliminating ambiguity in race ordering.
                cash_delta=ui['body']['delta']
                expected_balance=before['balance']+cash_delta+net
                expected_hwm=link['starting_balance']+cash_delta
                good=len(hist)==1 and abs(after['balance']-expected_balance)<.011 and abs(newlink['starting_balance']-expected_hwm)<.011
                return good,{'before':before,'after':after,'ui':ui,'close':close,'history':hist,'shares':shares,'commission':commission,
                    'expected_balance':expected_balance,'actual_balance':after['balance'],'expected_hwm':expected_hwm,'actual_hwm':newlink['starting_balance']}
            self.check(f'RACE-GUI-LEDGER-{i+1}','GUI balance edit versus master close: cash delta, settlement and HWM reconcile',race)
        self.ui.balance(email,1000000)

    def sell_bracket_retest(self):
        self.live_brackets(sides=('SELL',),distance=5)

    def live_brackets(self,sides=('BUY','SELL'),distance=20):
        self.cleanup()
        for side in sides:
            def exit_case(side=side):
                r=self.require_open(side,qty=.02);data=self.wait_fleet(1);oid=self.order_id(r)
                position=self.positions(MASTER_EMAIL)['positions'][0]
                price=position['current_price']
                # Close brackets around current market; monitor actual live tick execution.
                sl=round(price-distance if side=='BUY' else price+distance,2)
                tp=round(price+distance if side=='BUY' else price-distance,2)
                edit=self.api(MASTER_EMAIL,'PUT',f'positions/{oid}/protection',{'sl':sl,'tp':tp})
                if edit['http']!=200:
                    self.close(MASTER_EMAIL,oid);self.flat();raise RuntimeError('Market moved before bracket placement: '+str(edit))
                deadline=time.monotonic()+45
                while time.monotonic()<deadline and self.positions(MASTER_EMAIL)['count']:
                    time.sleep(1)
                master=self.positions(MASTER_EMAIL)
                if master['count']:
                    self.close(MASTER_EMAIL,oid);self.flat();raise RuntimeError('No natural SL/TP hit within 45 seconds; not a platform failure')
                remaining=self.flat()
                def rows(email):
                    pid=data[email]['positions'][0]['position_id']
                    return [h for h in self.read(email,'history')['history'] if h.get('position_id')==pid]
                history=dict(zip(ACCOUNTS,self.pool.map(rows,ACCOUNTS)))
                bad={e:h for e,h in history.items() if len(h)!=1 or abs(h[0]['qty']-.02)>1e-8}
                return not remaining and not bad,{'master_history':history[MASTER_EMAIL],'history_errors':bad,'orphans':remaining,'history':history}
            self.check('LIVE-BRACKET-'+side,'Natural live-market SL/TP exit closes copied positions exactly once',exit_case)
            self.cleanup()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--stages',default='protection_retest,accounting,balance_race_accounting,live_brackets,finish')
    args=parser.parse_args();qa=DeepQA()
    source=Path(__file__).read_bytes()
    (OUT/f'additional_source_{qa.run_id}.py').write_bytes(source)
    try:
        qa.authenticate()
        for stage in args.stages.split(','):getattr(qa,stage)()
    except Exception as e:
        (OUT/f'abort_{qa.run_id}.json').write_text(json.dumps({'time':now(),'status':'BLOCKED','error':str(e)},indent=2),encoding='utf-8')
        raise
    finally:
        if qa.ui:qa.ui.close()
        qa.pool.shutdown()
    return int(any(r['status']!='PASS' for r in qa.results))


if __name__=='__main__':sys.exit(main())
