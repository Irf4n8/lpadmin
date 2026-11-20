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
        for qty,mult in [(.01,.25),(.03,.5),(.01,1.5),(.01,2.75)]:
            def case(qty=qty,mult=mult):
                self.configure([email],multiplier=mult)
                r=self.require_open(qty=qty);time.sleep(1)
                child=self.positions(email)
                invalid=[p for p in child['positions'] if p['net_qty']<.01-1e-9 or abs(p['net_qty']/.01-round(p['net_qty']/.01))>1e-7]
                self.close(MASTER_EMAIL,self.order_id(r));remaining=self.flat();self.configure([email])
                return not invalid and not remaining,{'master_qty':qty,'multiplier':mult,'unrounded_product':qty*mult,
                    'child_positions':child['positions'],'invalid_entry_quantities':invalid,'orphans':remaining,
                    'oracle':'Live entry rejection established BLACK:BTCUSD minimum and step = 0.01; skip or valid rounding allowed'}
            self.check(f'SIZE-LOT-RULE-{qty}-{mult}','Copied new entry respects BLACK BTCUSD lot minimum and step',case)
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

    def live_brackets(self):
        self.cleanup()
        for side in ('BUY','SELL'):
            def exit_case(side=side):
                r=self.require_open(side,qty=.02);data=self.wait_fleet(1);oid=self.order_id(r)
                position=self.positions(MASTER_EMAIL)['positions'][0]
                price=position['current_price']
                # Close brackets around current market; monitor actual live tick execution.
                sl=round(price-20 if side=='BUY' else price+20,2)
                tp=round(price+20 if side=='BUY' else price-20,2)
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
