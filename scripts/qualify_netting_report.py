"""Reconcile accepted-order accounting, retain the raw run and group netting findings."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from test_suite.fresh_netting_staging_runner import NettingRun, EXPECTED


def main():
    report=json.loads((ROOT/'reports/netting_latest.json').read_text())
    if report['phase']!='COMPLETE':raise RuntimeError('Netting execution is not complete')
    out=Path(report['evidence_directory'])
    audit=json.loads((out/'fixture_after.json').read_text())
    if not audit['restored']:raise RuntimeError('Fresh accounts not restored')
    if not (out/'execution_raw.json').exists():
        (out/'execution_raw.json').write_text(json.dumps(report,indent=2))
    logs=json.loads((out/'requests.json').read_text())
    assert not any('/mam/' in x.get('path','') or '/pamm/' in x.get('path','') for x in logs)
    rows={r['tc_id']:r for r in report['cases']}
    for row in rows.values():
        sid=row['tc_id'].split('-')[-1]
        row['expected']=EXPECTED[sid]
        row['script']='test_suite/fresh_netting_staging_runner.py'
        if row['tc_id'].startswith(('NT-A-','NT-B-')):
            book=row['tc_id'].split('-')[1].lower()
            row['reproduce_command']=f'.venv/bin/python test_suite/fresh_netting_staging_runner.py --confirm-staging --accounts reports/netting_fresh_accounts.json --books {book} --only {sid} --recheck'
    race=rows['NT-A-C1']
    if race['status']=='FAIL':
        lo=rows['NT-A-P1']['evidence'][0];hi=race['evidence'][0]
        requests=[r for r in logs[lo:hi] if r.get('method')=='POST' and r.get('path','').endswith('/orders')]
        accepted=[r for r in requests if r['status']==200]
        expected=round(sum(r['payload']['qty']*(1 if r['payload']['side']=='BUY' else -1) for r in accepted),8)
        rejected=[{'http':r['status'],'side':r['payload']['side'],'response':r['response']} for r in requests if r['status']!=200]
        race['accepted_order_analysis']=dict(accepted=len(accepted),accepted_net_qty=expected,rejected=rejected)
        original=race.setdefault('raw_test_detail',race['actual'])
        follower_detail=original.split('followers match model:',1)[-1]
        race['actual']=f'Accepted{len(accepted)}/10 master requests; accepted-order net target={expected}; follower model mismatch: {follower_detail}; explicit LP-busy/other rejections={len(rejected)}. See accepted-order analysis and raw run.'
        buys=sum(r['payload']['side']=='BUY' for r in accepted);sells=sum(r['payload']['side']=='SELL' for r in accepted)
        race['remarks']+=f' Accepted-order analysis: net={expected} from{buys} accepted BUY and{sells} accepted SELL; recorded follower quantities must match this net times the ratio. LP-busy rejections alone are not treated as quantity drift.'
        (out/'a_book_race_analysis.json').write_text(json.dumps(race['accepted_order_analysis'],indent=2))
    recheck_path=ROOT/'reports/netting_recheck_latest.json'
    if recheck_path.exists():
        recheck=json.loads(recheck_path.read_text())
        if recheck['phase']=='COMPLETE':
            check=next(r for r in recheck['cases'] if r['tc_id']=='NT-A-C1')
            rounds=check.get('repetitions',[])
            race['targeted_recheck']={'report':'netting_recheck_execution.html','rounds':len(rounds),
                                     'failed_rounds':sum(r['status']=='FAIL' for r in rounds),'result':check['status']}
            race['remarks']+=' Targeted accepted-order-aware recheck: '+str(race['targeted_recheck'])
    obj=NettingRun.__new__(NettingRun)
    obj.rows=rows;obj.out=out;obj.start=report['started_at'];obj.phase='COMPLETE';obj.accounts=report['accounts']
    obj.instances=report['instances'];obj.inst='real-net';obj.logs=logs;obj.publish='netting'
    obj.save()
    if recheck_path.exists():
        p=ROOT/'reports/netting_execution.html'
        text=p.read_text().replace('</html>','<p><a href="netting_recheck_execution.html">Isolated A-book race recheck</a> uses accepted-order accounting and retains each round separately.</p></html>')
        p.write_text(text)
    groups={}
    for row in rows.values():
        if row['status']=='FAIL' and row['tc_id'].startswith(('NT-A-','NT-B-')):
            groups.setdefault(row['tc_id'].split('-')[-1],[]).append(row)
    findings=[]
    names={'N5':'Netting followers do not receive master TP/SL protection','P1':'Netting pending orders are not mirrored to followers',
           'C1':'A-book netting follower exposure diverges from accepted master trades'}
    for sid,failed in groups.items():
        findings.append(dict(id='SPEC-CT-NET-'+sid,date='2026-11-20',module='Copy Trading / Netting',
            bug_found=names.get(sid,'Netting '+sid+' invariant failed'),
            description=' | '.join(r['tc_id']+': '+r['actual'] for r in failed),
            proof_img='',proof_vid='',type='Bug',source_classification='Fresh-account Copy Trading netting execution',
            status='Open',verification='Independently observed on fresh staging accounts',severity='High',
            related_cases=[r['tc_id'] for r in failed],
            remarks='Per-case scripts and commands in netting report. MAM/PAMM excluded. External LP ledger evidence remains separately unverified.'))
    (ROOT/'reports/netting_defects.json').write_text(json.dumps(findings,indent=2))
    print('Netting functional results:',report['functional_summary'],'; grouped findings:',len(findings))


if __name__=='__main__':main()
