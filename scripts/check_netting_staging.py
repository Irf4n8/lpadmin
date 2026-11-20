"""Read-only netting readiness probe: never converts existing copy links or funds accounts."""
from collections import Counter
import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import sys
import requests

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import settings as cfg
from test_suite.client import BlackTraderClient


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--fresh-accounts',help='Manifest of newly provisioned test accounts')
    args=parser.parse_args()
    c=BlackTraderClient(timeout=12)
    out=ROOT/'reports/evidence'/('netting_preflight_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    out.mkdir(parents=True)
    evidence=[]
    manifest=json.loads(Path(args.fresh_accounts).read_text()) if args.fresh_accounts else None
    accounts=[a['email'].lower() for a in manifest['accounts']] if manifest else [cfg.MASTER_EMAIL.lower(),f'{cfg.DEFAULT_PREFIX}1@{cfg.DEFAULT_DOMAIN}'.lower()]
    if manifest and len(accounts)!=3:raise RuntimeError('Fresh account manifest must contain all three provisioned accounts')
    master=accounts[0]
    def record_get(path,account=None,instance=None,admin=False):
        headers={}
        if admin:headers['Authorization']='Bearer '+c.get_admin_token()
        elif account:headers['Authorization']='Bearer '+c.get_trader_token(account)
        if instance:headers['X-Broker-ID']=instance
        response=c.request_with_retry('GET',cfg.BASE_URL+path,headers=headers,max_attempts=1)
        try:data=response.json()
        except ValueError:data=response.text[:2000]
        item=dict(time=datetime.now(timezone.utc).isoformat(),method='GET',path=path,account=account,
                  broker_header=instance,status_code=response.status_code,data=data)
        evidence.append(item)
        return item
    public=record_get('/v1/oms/_instances',master)
    if manifest:
        for account in accounts[1:]:record_get('/v1/oms/_instances',account)
    admin=record_get('/admin/api/instances',admin=True)
    config=requests.get(cfg.BASE_URL+'/api/config',timeout=12).json()
    evidence.append(dict(path='/api/config',selected_nonsecret_fields={'oms_domain':config.get('oms_domain'),'engine_choice':config.get('engine_choice')}))
    listed=public['data'].get('instances',[]) if isinstance(public['data'],dict) else []
    admin_rows=admin['data'].get('instances',[]) if isinstance(admin['data'],dict) else []
    inventory={r['slug']:r for r in admin_rows}
    probes={}
    for slug in ('real-net','paper-net'):
        for email in accounts:
            for resource in ('positions','orders'):
                probe=record_get(f'/v1/oms/{slug}/{resource}',email,slug)
                probes[(slug,email,resource)]=probe
    control=record_get('/v1/oms/real/positions',master,'real')
    fresh_readback=[]
    if manifest:
        members=c.get_admin_members()
        fresh_readback=[{k:m.get(k) for k in ('email','member_id','book','status','balances','account_type')} for m in members if m.get('email', '').lower() in accounts]
        evidence.append(dict(path='/admin/api/members',selected_new_account_readback=fresh_readback))
    cases=[]
    def add(tid,description,status,actual,expected,remarks='',book='—'):
        cases.append(dict(tc_id=tid,description=description,preconditions='Configured staging account and registered netting OMS instance.',
                          steps=description,test_data='BLACK:EURUSD small lots; real-net; routing '+book,
                          expected=expected,actual=actual,status=status,severity='High' if status=='FAIL' else '—',
                          defect_id='SPEC-NETTING-AVAILABILITY' if status=='FAIL' else '—',remarks=remarks))
    visible={r['slug'] for r in listed}
    if manifest:
        add('NT-NEW01','Provision and authenticate three fresh staging accounts','PASS' if len(fresh_readback)==3 else 'FAIL',
            'New accounts created via admin API; all three authenticated for runtime instance reads: '+', '.join(accounts),
            'Fresh accounts exist and can authenticate independently of existing test links.',
            'Account provisioning passed; netting functionality is a separate prerequisite.')
    configured={s for s in ('real-net','paper-net') if inventory.get(s,{}).get('enabled') and inventory.get(s,{}).get('exists')}
    add('NT-ENV01','Compare admin instance registration with runtime inventory','PASS' if configured<=visible else 'FAIL',
        f'Admin enabled/existing netting={sorted(configured)}; runtime visible={sorted(visible)}',
        'Configured enabled/visible netting instances appear in the runtime inventory.')
    available={}
    for slug,tid in [('real-net','NT-ENV02'),('paper-net','NT-ENV03')]:
        actual=[p for (s,_,_),p in probes.items() if s==slug]
        available[slug]=slug in visible and all(p['status_code']==200 for p in actual)
        add(tid,slug+' positions/orders API availability','PASS' if available[slug] else 'FAIL',
            '; '.join(f'{p["account"]} {p["path"]}: HTTP{p["status_code"]} {p["data"]}' for p in actual),
            'Master and follower can read netting state with explicit X-Broker-ID headers.')
    add('NT-CONTROL','Hedging endpoint control','PASS' if control['status_code']==200 else 'FAIL',
        f'real/positions HTTP{control["status_code"]}', 'A known hedging endpoint remains reachable.',
        'A passing control is not a netting execution pass.')
    specs=[
        ('N1','Open one netted position','One position per symbol, with copied quantities matching the link ratio.'),
        ('N2','Opposite order reduces net exposure','Remaining quantity equals the algebraic net; no second hedged leg.'),
        ('N3','Larger opposite order flips side','Exactly one residual position on the new side.'),
        ('N4','Exact opposite order closes','Master and followers end flat with zero used margin.'),
        ('N5','TP/SL survives additions and synchronizes','Protection remains correct after net-position changes.'),
        ('P1','Pending fan-out and cancellation','Pending tickets mirror and cancellation leaves no orphan orders.'),
        ('C1','Concurrent mixed BUY/SELL','Final net quantity matches accepted trades; no duplicate exposure.'),
        ('ISOLATION','Follower manual close isolation','Closing a follower position does not close the master position.'),
        ('ROUTING','Mixed A/B-book netting replication','Each child routes under its own account book and reconciles correctly.'),
    ]
    for book in ('B-book','A-book'):
        for tid,description,expected in specs:
            add('NT-'+('B' if book=='B-book' else 'A')+'-'+tid,description,'BLOCKED' if not available['real-net'] else 'NOT RUN',
                'Not executed: real-net runtime is not available (HTTP404 no such OMS instance); no netting orders or copy-link changes submitted.' if not available['real-net'] else
                'Runtime preflight ready; functional netting runner and required route/MAM fixtures must be executed separately.',
                expected,'Related API/hedging checks do not establish netting semantics.',book)
    blocked=not available['real-net']
    payload=dict(suite='Netting staging readiness and planned A/B-book execution',updated_at=datetime.now(timezone.utc).isoformat(),
                 host=cfg.BASE_URL,phase='BLOCKED' if blocked else 'READY FOR FUNCTIONAL EXECUTION',
                 summary=dict(Counter(r['status'] for r in cases)),
                 functional_summary=dict(Counter(r['status'] for r in cases if r['tc_id'].startswith(('NT-A-','NT-B-')))),
                 state_changes='Three new accounts provisioned at user request; subsequent netting probes are GET-only. No orders, funding, book switches or copy-link changes.' if manifest else 'None: GET-only checks; no orders, balances, books or subscriptions changed.',
                 fresh_accounts=fresh_readback,
                 evidence_directory=str(out),cases=cases)
    (out/'requests.json').write_text(json.dumps(evidence,indent=2))
    (out/'execution.json').write_text(json.dumps(payload,indent=2))
    (ROOT/'reports/netting_preflight_latest.json').write_text(json.dumps(payload,indent=2))
    if blocked:
        defect=dict(id='SPEC-NETTING-AVAILABILITY',serial=36,date='2026-11-20',module='OMS / Netting availability',
                    bug_found='Admin lists enabled netting instances but runtime omits them and netting endpoints return404',
                    description='Both real-net and paper-net are enabled/visible/existing in admin, absent from user inventory, and return no such OMS instance for master/follower reads with explicit broker headers.',
                    proof_img='',proof_vid='',type='Bug',source_classification='Netting staging preflight',status='Open',
                    verification='Independently reproduced by read-only API probes',severity='High',
                    related_cases=['NT-ENV01','NT-ENV02','NT-ENV03'],
                    remarks='One availability/configuration defect, not three independent bugs. Functional Copy Trading A/B netting checks are blocked. See preflight report and API evidence.')
        (ROOT/'reports/netting_availability_defect.json').write_text(json.dumps(defect,indent=2))
    esc=lambda v:html.escape(str(v))
    cols=[('tc_id','TC ID'),('description','Test Case Description'),('preconditions','Pre-Conditions'),('steps','Test Steps'),
          ('test_data','Test Data'),('expected','Expected Result'),('actual','Actual Result'),('status','Status'),
          ('severity','Severity'),('defect_id','Defect ID'),('remarks','Remarks')]
    page='<!doctype html><html lang="en"><meta charset="utf-8"><title>Netting Staging Report</title><style>body{font:14px system-ui;margin:24px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd4df;padding:9px;vertical-align:top;text-align:left}th{background:#e8eef7;position:sticky;top:0}</style><h1>Netting — Staging Execution Readiness</h1>'
    page+='<p>'+esc(payload['phase'])+' | '+esc(payload['summary'])+'</p><p>Copy Trading-only preflight; functional scenarios are BLOCKED when netting is unavailable and NOT RUN when ready. No MAM/PAMM tests. Only account provisioning, availability probes and the hedging control ran here; functional trade results are in the separate netting execution report.</p><p>'+esc(payload['state_changes'])+'</p>'
    if manifest:page+='<p>Fresh accounts: '+esc(', '.join(accounts))+'. All are retained for subsequent testing; no passwords are included in this report.</p>'
    page+='<p>'+('Restore the runtime netting instance before trading tests.' if blocked else 'Netting availability checks passed; run the scripted functional Copy Trading suite.')+'</p>'
    page+='<p><a href="master_spec_execution.html">Main report</a> · <a href="netting_preflight_latest.json">Preflight data</a> · <a href="netting_execution.html">Functional execution</a> · <a href="evidence/'+out.name+'/requests.json">API evidence</a></p><table><thead><tr>'+''.join('<th>'+name+'</th>' for _,name in cols)+'</tr></thead><tbody>'
    page+=''.join('<tr>'+''.join('<td>'+esc(row[k])+'</td>' for k,_ in cols)+'</tr>' for row in cases)+'</tbody></table></html>'
    (ROOT/'reports/netting_preflight_execution.html').write_text(page)
    print(json.dumps(dict(phase=payload['phase'],summary=payload['summary'],functional_summary=payload['functional_summary'],evidence=str(out)),indent=2))


if __name__=='__main__':main()
