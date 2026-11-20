"""Import the user's dated bug list without presenting unverified reports as reproduced."""
import html
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DATA=[
('2026-11-11','Workspace','Previous user account workspace can be copied','','UI'),
('2026-11-11','Copy Trading / MAM / PAMM','Managers cannot see their own CT, MAM and PAMM entries in the managers list','','UI'),
('2026-11-12','Admin','Add-member email dialog closes when dragging to select/copy email text','','UI'),
('2026-11-12','Trades / Broker settings','Opening the same real-only account in another tab displays paper trading','','UI'),
('2026-11-13','Watchlist / Chart','Trading a watchlist symbol does not open the chart module','','Feature'),
('2026-11-13','MAM','Follower trades/P&L and follower selection should be available in a dropdown','','Feature'),
('2026-11-13','Copy Trading / Routing','A-book master orders are not copied to B-book followers through B-book routing','','Bug'),
('2026-11-13','Admin / Routing','B-to-A follower book switch is blocked for open orders when only the master has open orders','','Bug'),
('2026-11-13','Positions UI','Balance footer moves or becomes misaligned when repositioning trades with all four broker settings enabled','','UI'),
('2026-11-13','MAM / Netting','Master orders are not copied to MAM followers in real netting','','Bug'),
('2026-11-13','Orders / TP-SL validation','Absurd TP/SL values are accepted','tp=-1 and sl=1e30 reportedly return HTTP 200.','UI'),
('2026-11-16','Broker settings','Broker preferences do not persist across devices or incognito sessions','Reported preferences appear to be saved only locally.',''),
('2026-11-16','Copy Trading / Netting','Closing a follower order also closes the master order','',''),
('2026-11-16','Copy Trading / Master UI','History and Active views are missing for copy-trading masters but available for MAM','',''),
('2026-11-16','MAM / History','View Trades is not displayed for previous followers in master follower history','',''),
('2026-11-16','Copy Trading / Load','Master and follower order counts differ when placing 200+ orders','',''),
('2026-11-16','Orders / Routing','Liquidity-provider error appears when placing a B-book order','',''),
('2026-11-17','Copy Trading / Sizing','Multiplier zero is accepted and silently stored as 1x','Expected zero to be rejected like -1.',''),
('2026-11-17','Pending orders','Wrong edit field names return success without changing the order','',''),
('2026-11-17','Symbol information / Order entry','Minimum volume differs between symbol info, one-tap order and buy/sell window','Reported one-tap minimum 0.01 versus buy/sell minimum 0.00001.',''),
('2026-11-17','Copy Trading / Minimum volume','Sub-minimum follower quantity is rounded up instead of cancelled','Reported master 0.001, computed follower 0.00025; user reports forced minimum/master-size exposure, also citing 0.01. Exact symbol and units need confirmation.',''),
('2026-11-17','Copy Trading / Benchmark','Unfollow and re-follow overwrites the benchmark','Follower can manipulate the benchmark by unfollowing/re-following while in profit.',''),
('2026-11-17','Orders / Quantity validation','API accepts quantities beyond UI minimum/maximum constraints','',''),
('2026-11-18','Orders / TP-SL validation','API TP/SL inputs lack the UI constraints','',''),
('2026-11-18','Orders / Input validation','Unknown or misspelled MARKET order type returns HTTP 500 instead of 400','',''),
('2026-11-18','Admin / Balance','Negative user balances can be set, producing negative balance and free margin','Reported example balance=-2121.',''),
('2026-11-18','Copy Trading / Unsubscribe','Follower orders are cancelled after unfollowing the master','',''),
('2026-11-18','Pending orders / Margin','Pending-order margin reservation policy is unclear','User asks whether margin should be locked for pending orders.',''),
('2026-11-18','Wallet / Deposit history','Wallet deposit appears twice in the display','',''),
('2026-11-19','Copy Trading / Multiplier validation','Multiplier accepts excessive decimal precision','Reported range 0.1–100 permits a value such as 99.092809812.',''),
]


def main():
    output=ROOT/'reports/bug_register.json'
    previous=json.loads(output.read_text()) if output.exists() else {'bugs':[]}
    bugs=[]
    for number,(date,module,title,description,source_type) in enumerate(DATA,1):
        bug=dict(id=f'BUG-{number:03}',serial=number,date=date,module=module,bug_found=title,
                 description=description or title,proof_img='',proof_vid='',type='Bug',source_classification=source_type,
                 status='Open',verification='User-reported; not independently reproduced in this update',
                 severity='Untriaged',related_cases=[],remarks='')
        if source_type=='Feature':bug['remarks']='Originally listed as Feature; logged as a bug per the latest instruction. Expected behavior needs product confirmation.'
        if number==18:
            bug.update(verification='Independently reproduced on staging, 2026-11-20',severity='High',related_cases=['CT-C007'],
                       remarks='Same defect as SPEC-C007; one canonical register entry, not an additional duplicate.')
        if number==20:
            bug['proof_img']='https://drive.google.com/file/d/1QSPJVcBCpLC9QFBJRryMgzixtDFyF5Jf/view?usp=drive_link'
        if number==29:
            bug['proof_img']='https://drive.google.com/file/d/1ie5gNKCcaU4gvzbXM3E4shxDnKIEQKmQ/view?usp=drive_link'
        if number in (21,28,30):
            bug['verification']='User-reported; policy/expected-behavior clarification required'
        if number==21:
            bug.update(related_cases=['CT-N005'],remarks='Rounding up to broker minimum was observed in staging. The supplied master specification permits round-up or safe skipping; the requested cancellation-only policy differs. Not declared fixed or a confirmed implementation defect.')
        if number==23:
            bug.update(related_cases=['CT-N005','CT-N006'],remarks='The 20 Nov sampled tests enforced BTC minimum and EURUSD maximum/capping. The reported API/UI mismatch remains open for its exact symbol, endpoint and values; not marked fixed.')
        if number==16:bug['remarks']='Earlier burst checked at most 20 concurrent orders; it does not verify the reported 200+ scale.'
        if number==27:bug['remarks']='Whether cancellation is a defect depends on the selected unsubscribe keep/close/cancel policy; retain as open pending policy-specific reproduction.'
        if number==28:bug['remarks']='Logged as a bug candidate per instruction; margin-reservation requirements must be confirmed before assigning a failed test.'
        if number==30:bug['remarks']='Precision and rounding requirements are not specified; numeric range compliance alone does not establish a bug.'
        bugs.append(bug)
    # Retain the other five independently observed failures alongside the user's list.
    report=json.loads((ROOT/'reports/master_spec_latest.json').read_text())
    for row in report['cases']:
        if row['status']!='FAIL' or row['tc_id']=='CT-C007':continue
        bugs.append(dict(id=row['defect_id'],serial=len(bugs)+1,date='2026-11-20',module=row['tc_id'],
                         bug_found=row['description'],description=row['actual'],proof_img='',proof_vid='',type='Bug',
                         source_classification='Automated staging execution',status='Open',verification='Independently observed; see execution evidence',
                         severity=row['severity'],related_cases=[row['tc_id']],remarks=row['remarks']))
    ab_path=ROOT/'reports/a_book_latest.json'
    if ab_path.exists():
        ab=json.loads(ab_path.read_text())
        if ab['phase']=='COMPLETE':
            ac={row['tc_id']:row for row in ab['cases']}
            for number,tid in [(7,'AB004'),(8,'AB016')]:
                bug=next(b for b in bugs if b['id']==f'BUG-{number:03}')
                bug['related_cases']=list(dict.fromkeys(bug['related_cases']+[tid]))
                if ac[tid]['status']=='PASS':
                    bug['verification']='Not reproduced in sampled staging A-book routing check; original report remains open'
                    bug['remarks']+=' '+tid+' passed on 20 Nov with admin book flags read back. Independent external LP/broker execution remains unverified; this is not a declaration that the original issue is fixed.'
                elif ac[tid]['status']=='FAIL':
                    bug['verification']='Independently reproduced in staging A-book routing check'
                    bug['remarks']+=' See '+tid+' and A-book API evidence.'
            for row in ab['cases']:
                if row['status']!='FAIL' or row['tc_id'] in ('AB004','AB016'):continue
                bugs.append(dict(id=row['defect_id'],serial=len(bugs)+1,date='2026-11-20',module='A-book / Routing',
                                 bug_found=row['description'],description=row['actual'],proof_img='',proof_vid='',type='Bug',
                                 source_classification='A-book staging execution',status='Open',
                                 verification='Independently observed; external broker scope stated in A-book report',
                                 severity=row['severity'],related_cases=[row['tc_id']],remarks=row['remarks']))
    net_path=ROOT/'reports/netting_latest.json'
    if net_path.exists():
        net=json.loads(net_path.read_text())
        if net.get('phase')=='COMPLETE':
            nc={r['tc_id']:r for r in net['cases']}
            isolation=[nc[k] for k in ('NT-B-ISOLATION','NT-A-ISOLATION') if k in nc]
            bug=next(b for b in bugs if b['id']=='BUG-013')
            bug['related_cases']=list(dict.fromkeys(bug['related_cases']+[r['tc_id'] for r in isolation]))
            if isolation and all(r['status']=='PASS' for r in isolation):
                bug['verification']='Not reproduced in sampled fresh-account Copy Trading netting isolation checks; remains open'
                bug['remarks']+=' Master and second follower remained unchanged after follower1 closed its copied position in both book phases. MAM/PAMM were not tested.'
            findings_path=ROOT/'reports/netting_defects.json'
            if findings_path.exists():
                for finding in json.loads(findings_path.read_text()):
                    bugs.append({**finding,'serial':len(bugs)+1})
    # Preserve future manually added entries on repeated imports.
    known={b['id'] for b in bugs}
    bugs += [b for b in previous['bugs'] if b['id'] not in known]
    payload=dict(updated_on='2026-11-20',user_reported_count=len(DATA),total_unique_entries=len(bugs),
                 current_execution_scope='Copy Trading only; MAM/PAMM excluded. Historical user-reported entries are retained without claiming new execution.',
                 note='Reported issues are logged as open bugs, not automatically treated as reproduced or as new failed test cases. Proof links are user-supplied and have not been opened or independently verified.',bugs=bugs)
    output.write_text(json.dumps(payload,indent=2,ensure_ascii=False))
    esc=lambda x:html.escape(str(x))
    headers=['S.No','Date','Module','Bug Found','Bug Description','Proof - IMG','Proof - VID','Bug / Feature','Remarks','Bug ID','Verification','Severity']
    body=''
    for b in bugs:
        image='<a href="'+esc(b['proof_img'])+'">User-supplied screenshot</a>' if b['proof_img'] else '—'
        fields=[b['serial'],b['date'],b['module'],b['bug_found'],b['description'],None,b['proof_vid'] or '—',b['type'],b['remarks'],b['id'],b['verification'],b['severity']]
        body+='<tr>'+''.join('<td>'+ (image if i==5 else esc(v))+'</td>' for i,v in enumerate(fields))+'</tr>'
    page='<!doctype html><html lang="en"><meta charset="utf-8"><title>Bug Register</title><style>body{font:14px system-ui;margin:24px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd4df;padding:9px;text-align:left;vertical-align:top}th{background:#e8eef7;position:sticky;top:0}</style>'
    page+='<h1>Bug Register — 20 November 2026</h1><p>30 user-reported entries added; '+str(len(bugs))+' unique entries including the prior staging failures. All remain open. Reported issues have not all been reproduced. Original Feature/UI classifications are retained in the JSON; all are logged as bugs per instruction.</p>'
    page+='<p>Screenshot links are supplied evidence references; their contents have not been independently reviewed. No videos were supplied.</p><table><thead><tr>'+''.join('<th>'+h+'</th>' for h in headers)+'</tr></thead><tbody>'+body+'</tbody></table></html>'
    (ROOT/'reports/bug_register.html').write_text(page)
    assert len(DATA)==30 and len({b['id'] for b in bugs})==len(bugs)
    assert sum(bool(b['proof_img']) for b in bugs)==2
    print(f'Added {len(DATA)} user-reported rows; {len(bugs)} unique open register entries. Preserved both screenshot links.')


if __name__=='__main__':main()
