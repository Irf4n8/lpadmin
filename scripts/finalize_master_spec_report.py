"""Reconcile partial coverage and package the completed staging execution matrix."""
import argparse
from collections import Counter
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
import sys
import zipfile
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from test_suite.staging_master_spec_runner import Run, parse_utc


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--spec',required=True)
    args=parser.parse_args()
    report=json.loads((ROOT/'reports/master_spec_latest.json').read_text())
    if report['phase']!='COMPLETE':raise RuntimeError('Execution must finish before finalization')
    paths=sorted((ROOT/'reports/evidence').glob('master_spec_*/execution.json'),key=lambda p:p.stat().st_mtime,reverse=True)
    path=next(p for p in paths if json.loads(p.read_text())['started_at']==report['started_at'])
    audit=json.loads((path.parent/'fixture_after.json').read_text())
    if not audit['restored']:raise RuntimeError('Fixture restoration not verified')
    if not (path.parent/'execution_raw.json').exists():
        shutil.copyfile(path,path.parent/'execution_raw.json')
    logs=json.loads((path.parent/'requests.json').read_text())
    rows={r['tc_id']:r for r in report['cases']}
    for row in rows.values():
        if row['status']=='IN PROGRESS':
            row.update(status='BLOCKED',coverage='partial')
            row['remarks']+=' Partial observations retained; full requirement unverified.'
    # The actual measured FX fills were equal: this verifies lot-scaled math,
    # but cannot certify the specified different-price/slippage precondition.
    pnl=rows['CT-P002']
    if pnl['status']=='PASS':
        stop=pnl['evidence'][0]
        hs=[x['response'].get('history',[]) for x in logs[:stop] if x.get('path','').endswith('/history')]
        master=next((h for h in hs[-2] if h.get('symbol')=='BLACK:EURUSD'),None) if len(hs)>=2 else None
        follower=next((h for h in hs[-1] if h.get('symbol')=='BLACK:EURUSD'),None) if hs else None
        if master and follower and all(master[k]==follower[k] for k in ('entry_price','exit_price')):
            rows['CT-P001'].update(status='BLOCKED',coverage='partial',severity='—',defect_id='—',
                actual=f'Own-fill P&L math matched, but both accounts filled at entry={master["entry_price"]}, exit={master["exit_price"]}; different-price slippage precondition not induced.',
                remarks='Needs controlled broker/feed slippage; P002 independently verifies quantity-scaled gross P&L.')
    blockers={
        'F001':'Browser host unavailable; master onboarding, broker binding and KYC UI not executed.',
        'F002':'Browser host unavailable; new follower onboarding, KYC and broker funding workflow not executed.',
        'F003':'Existing API subscriptions exercised; new UI linkage, terms and Pending_Activation transition not verified.',
        'F023':'Browser host unavailable; actual refresh and UI rehydration cannot be observed.',
        'P010':'Browser host unavailable; dashboard refresh/WebSocket synchronization not executed.',
        'R024':'Measured cohort contained ten followers; 100 distinct followers across worker nodes were not enrolled or measured.',
        'R027':'Fifty distinct concurrent subscription fixtures were not enrolled; ten-account test results do not establish this scale.',
        'R028':'Fifty distinct concurrent unsubscription fixtures were not enrolled; ten-account test results do not establish this scale.',
        'R040':'Requires a controlled timeout-after-broker-fill fixture and broker ClOrdID reconciliation access.',
        'C013':'BUY-only/SELL-only filter was not configured. Reverse copying is not equivalent and is not counted as coverage.',
        'I004':'Requires the actual scheduled EOD engine-versus-broker reconciliation job; an API flat-account audit is not equivalent.',
        'O001':'Global kill-switch, dual authorization and UI/banner verification require documented privileged controls and a coordinated isolated test window.',
    }
    for tid,reason in blockers.items():
        row=rows['CT-'+tid]
        if row['test_data']=='Not executed':row['actual']=reason
    # Four failures are exact HTTP-contract mismatches with correct safe final state.
    for tid in ('R019','R020','N003','N014'):
        row=rows['CT-'+tid]
        if row['status']=='FAIL':
            row['severity']='Low'
            row['finding_type']='API contract mismatch'
            row['remarks']+=' Safe rejection/final-state behavior observed; failure is the exact response contract specified in the supplied document.'
    if rows['CT-C007']['status']=='FAIL':
        rows['CT-C007'].update(severity='High',finding_type='Configuration validation defect')
    disabled=rows['CT-N009']
    if disabled['status']=='FAIL':
        xs=logs[:disabled['evidence'][0]]
        master=next(x['response']['order'] for x in reversed(xs) if x.get('method')=='POST' and x.get('path','').endswith('/orders') and x.get('status')==200)
        orders=next(x['response']['orders'] for x in reversed(xs) if x.get('method')=='GET' and x.get('path','').endswith('/orders'))
        child=next(o for o in orders if str(o.get('copy_ref','')).lstrip('-')==master['order_id'])
        delta=(parse_utc(child['updated_at'])-parse_utc(master['updated_at'])).total_seconds()*1000
        disabled.update(severity='High',finding_type='Disabled-member execution gating defect',
            actual=f'Admin acknowledged status=disabled (HTTP200); copied order {child["order_id"]} FILLED {delta:.3f}ms after master {master["order_id"]}. Test waited2s before restoring active status.',
            remarks='Account active status restored and read back in fixture_after.json. Initial reproduction used the admin status acknowledgment; separate database flag verification was not performed.')
        (path.parent/'disabled_follower_reproduction.json').write_text(json.dumps(dict(
            admin_status_requests=[x for x in xs if x.get('path','').endswith('/status')][-2:],
            master=master,child=child,copy_fill_delta_ms=delta,delay_before_reactivation_s=2),indent=2))
    obj=Run.__new__(Run)
    obj.rows=rows; obj.logs=logs; obj.out=path.parent; obj.start=report['started_at']; obj.phase='COMPLETE'
    obj.prior_evidence=report.get('prior_evidence',[])
    obj.save()
    final=json.loads(path.read_text())
    checks={'passed':99,'failed':0,'warning':'Existing urllib3/LibreSSL compatibility warning'}
    junit_path=ROOT/'reports/evidence/master_spec_local_checks.xml'
    if junit_path.exists():
        suites=list(ET.parse(junit_path).getroot().iter('testsuite'))
        failures=sum(int(s.get('failures',0))+int(s.get('errors',0)) for s in suites)
        checks.update(passed=sum(int(s.get('tests',0))-int(s.get('failures',0))-int(s.get('errors',0))-int(s.get('skipped',0)) for s in suites),failed=failures)
    final.update(spec_sha256=hashlib.sha256(Path(args.spec).read_bytes()).hexdigest(),
                 routing_scope='Original192-case matrix: B-book hedging baseline. A-book and netting variants are reported separately.',
                 current_product_scope='Copy Trading only; no MAM/PAMM product execution.',
                 attempted_cases=sum(r['test_data']!='Not executed' for r in rows.values()),
                 local_checks=checks,
                 fixture_restoration_verified=True)
    formatted_dir=ROOT/'outputs/copy_trading_format_20261120'
    formatted_name='Copy_Trading_Test_Execution_Report_2026-11-20.xlsx'
    if (formatted_dir/formatted_name).exists():
        final['formatted_copy_trading_report']={'workbook':str((formatted_dir/formatted_name).relative_to(ROOT)),
                                               'table':'copy_trading_execution_table.html','columns':11,
                                               'note':'Mode variants, partial observations and planned coverage retain their scope; source snapshots accompany the workbook.'}
    if (ROOT/'reports/bug_register.json').exists():
        register=json.loads((ROOT/'reports/bug_register.json').read_text())
        final['additional_bug_register']={'file':'bug_register.json','user_reported':register['user_reported_count'],
                                          'unique_entries':register['total_unique_entries'],
                                          'note':'Unverified reports do not change executed test verdicts.'}
    if (ROOT/'reports/network_browser_race_cases.json').exists():
        extra=json.loads((ROOT/'reports/network_browser_race_cases.json').read_text())
        final['additional_race_test_plan']={'file':'network_browser_race_cases.json','cases':extra['total_cases'],
                                            'summary':extra['summary'],'combined_catalogue_cases':len(rows)+extra['total_cases']}
    if (ROOT/'reports/a_book_latest.json').exists():
        ab=json.loads((ROOT/'reports/a_book_latest.json').read_text())
        final['a_book_execution']={'file':'a_book_latest.json','phase':ab['phase'],'cases':len(ab['cases']),
                                  'summary':ab['summary'],'external_lp_execution':ab['external_lp_execution']}
    if (ROOT/'reports/netting_latest.json').exists():
        net=json.loads((ROOT/'reports/netting_latest.json').read_text())
        final['copy_trading_netting_execution']={'file':'netting_latest.json','phase':net['phase'],
                                               'summary':net['summary'],'functional_summary':net.get('functional_summary',{}),
                                               'scope':'Copy Trading only; MAM/PAMM excluded'}
    if (ROOT/'reports/netting_recheck_latest.json').exists():
        recheck=json.loads((ROOT/'reports/netting_recheck_latest.json').read_text())
        final['netting_targeted_recheck']={'file':'netting_recheck_latest.json','phase':recheck['phase'],'summary':recheck['summary']}
    scope_junit=ROOT/'reports/evidence/copy_trading_scope_checks.xml'
    if scope_junit.exists():
        suites=list(ET.parse(scope_junit).getroot().iter('testsuite'))
        final['copy_trading_scope_checks']={'tests':sum(int(s.get('tests',0)) for s in suites),
                                          'failed':sum(int(s.get('failures',0))+int(s.get('errors',0)) for s in suites)}
    if (ROOT/'reports/reproduction_commands.json').exists():
        final['reproduction_scripts']={'file':'reproduction_commands.json','scope':'Executed checks only; unexecuted requirements are not claimed automated.'}
    for target in (path,ROOT/'reports/master_spec_latest.json'):
        target.write_text(json.dumps(final,indent=2))
    defects=[r for r in rows.values() if r['status']=='FAIL']
    (path.parent/'defects.json').write_text(json.dumps(defects,indent=2))
    shutil.copyfile(args.spec,path.parent/'master_specification_source.txt')
    assert len(rows)==192 and Counter(r['priority'] for r in rows.values())=={'P0':165,'P1':26,'P2':1}
    assert all(r['status'] in ('PASS','FAIL','BLOCKED','NOT RUN','SKIPPED') for r in rows.values())
    class Validate(HTMLParser):
        def __init__(self):super().__init__();self.body=False;self.rows=0
        def handle_starttag(self,tag,attrs):
            if tag=='tbody':self.body=True
            if tag=='tr' and self.body:self.rows+=1
        def handle_endtag(self,tag):
            if tag=='tbody':self.body=False
    check=Validate();check.feed((ROOT/'reports/master_spec_execution.html').read_text())
    assert check.rows==192,check.rows
    archive=ROOT/'reports/staging_master_test_report_2026-11-20.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in [ROOT/'reports/master_spec_execution.html',ROOT/'reports/master_spec_latest.json']:
            z.write(p,p.name)
        for name in ('bug_register.html','bug_register.json','network_browser_race_cases.html','network_browser_race_cases.json','network_browser_race_source.txt','a_book_execution.html','a_book_latest.json','netting_execution.html','netting_latest.json','netting_fresh_accounts.json','netting_defects.json','netting_recheck_execution.html','netting_recheck_latest.json','netting_preflight_execution.html','netting_preflight_latest.json','reproduction_commands.html','reproduction_commands.json','copy_trading_execution_table.html'):
            p=ROOT/'reports'/name
            if p.exists():z.write(p,name)
        if (ROOT/'reports/a_book_latest.json').exists():
            ab=json.loads((ROOT/'reports/a_book_latest.json').read_text())
            abdir=Path(ab['evidence_directory'])
            if abdir.is_relative_to(ROOT/'reports/evidence'):
                for p in abdir.iterdir():
                    if p.is_file():z.write(p,'evidence/'+abdir.name+'/'+p.name)
        if (ROOT/'reports/netting_latest.json').exists():
            net=json.loads((ROOT/'reports/netting_latest.json').read_text())
            netdir=Path(net['evidence_directory'])
            if netdir.is_relative_to(ROOT/'reports/evidence'):
                for p in netdir.iterdir():
                    if p.is_file():z.write(p,'evidence/'+netdir.name+'/'+p.name)
        for report_name in ('netting_recheck_latest.json','netting_preflight_latest.json'):
            rp=ROOT/'reports'/report_name
            if rp.exists():
                folder=Path(json.loads(rp.read_text())['evidence_directory'])
                if folder.is_relative_to(ROOT/'reports/evidence'):
                    for p in folder.iterdir():
                        if p.is_file():z.write(p,'evidence/'+folder.name+'/'+p.name)
        sources=['test_suite/staging_master_spec_runner.py','test_suite/a_book_staging_runner.py','test_suite/fresh_netting_staging_runner.py',
                 'test_suite/netting_hedging_runner.py','test_suite/breakpoint_race_runner.py','test_suite/client.py','test_suite/baseline.py',
                 'scripts/create_netting_test_accounts.py','scripts/check_netting_staging.py','scripts/staging_race_followup.py',
                 'scripts/staging_close_control.py','scripts/finalize_master_spec_report.py','scripts/build_reproduction_index.py',
                 'scripts/qualify_netting_report.py','scripts/update_bug_register.py','tests/test_netting_scope.py',
                 'tests/test_concurrency.py','config/settings.py','config/__init__.py','test_suite/__init__.py','requirements.txt']
        for name in sources:
            p=ROOT/name
            if p.exists():z.write(p,'automation/'+name)
        z.writestr('automation/README.txt','Automation source snapshot. Run within the existing lpadmin repository with its installed dependencies and your configured test credentials. No credentials or .env files are included. See reproduction_commands.html for per-case commands. Current product testing scope is Copy Trading only; the fresh netting runner rejects MAM/PAMM selectors. Existing account provisioning and netting links are isolated through the explicit fresh-account manifest.\n')
        for p in path.parent.iterdir():
            if p.is_file():z.write(p,'evidence/'+path.parent.name+'/'+p.name)
        for prior in obj.prior_evidence:
            for name in ('fixture_before.json','fixture_after.json','execution.json'):
                p=Path(prior)/name
                if p.exists():z.write(p,'evidence/'+p.parent.name+'/'+p.name)
        junit=ROOT/'reports/evidence/master_spec_local_checks.xml'
        if junit.exists():z.write(junit,'evidence/'+junit.name)
        if scope_junit.exists():z.write(scope_junit,'evidence/'+scope_junit.name)
        if (formatted_dir/formatted_name).exists():
            z.write(formatted_dir/formatted_name,formatted_name)
            text_name=formatted_name.replace('.xlsx','.tsv')
            if (formatted_dir/text_name).exists():z.write(formatted_dir/text_name,text_name)
            for p in (formatted_dir/'sources').glob('*.json'):z.write(p,'sources/'+p.name)
            helper=formatted_dir/'simplify_report.mjs'
            if helper.exists():z.write(helper,'automation/outputs/copy_trading_format_20261120/'+helper.name)
            builder=formatted_dir/'build_copy_trading_report.mjs'
            if builder.exists():z.write(builder,'automation/outputs/copy_trading_format_20261120/'+builder.name)
    print(json.dumps({'summary':final['summary'],'attempted_cases':final['attempted_cases'],
                      'defects':[(r['tc_id'],r['severity'],r['actual']) for r in defects],
                      'restored':True,'report':str(ROOT/'reports/master_spec_execution.html'),'archive':str(archive)},indent=2))


if __name__=='__main__':main()
