"""Attach real script commands to previously executed checks; do not invent automation coverage."""
import html
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    entries=[]
    source=next(p for p in sorted((ROOT/'reports/evidence').glob('master_spec_*/master_specification_source.txt')))
    source_arg='--spec '+str(source.relative_to(ROOT))
    base='.venv/bin/python test_suite/staging_master_spec_runner.py --confirm-staging '+source_arg
    group_map={**{x:'focused' for x in ('CT-F013','CT-R011','CT-F017','CT-N005','CT-N008','CT-F019')},
               **{x:'financial' for x in ('CT-P001','CT-P002','CT-P003','CT-F030')},
               **{x:'administrative' for x in ('CT-N006','CT-N009','CT-R023','CT-R054')}}
    master_path=ROOT/'reports/master_spec_latest.json'
    master=json.loads(master_path.read_text())
    for row in master['cases']:
        if row['test_data']=='Not executed':continue
        cmd=base
        if row['tc_id'] in group_map:cmd+=' --extend-latest --only-groups '+group_map[row['tc_id']]
        if row.get('script') in ('test_suite/copy_remaining_api_runner.py','test_suite/copy_browser_completion_runner.py','test_suite/copy_scale_completion_runner.py'):
            cmd=row['reproduce_command'].replace('<master-specification.txt>',str(source.relative_to(ROOT)))
            row['reproduce_command']=cmd
        else:row.update(script='test_suite/staging_master_spec_runner.py',reproduce_command=cmd)
        entries.append(dict(scope='Historical Copy Trading B-book matrix',tc_id=row['tc_id'],status=row['status'],
                            script=row['script'],command=cmd,notes='Uses the originally configured test cohort; group/full-suite command includes this case. Partial evidence remains partial.'))
    master_path.write_text(json.dumps(master,indent=2))
    ab_path=ROOT/'reports/a_book_latest.json'
    if ab_path.exists():
        ab=json.loads(ab_path.read_text())
        for row in ab['cases']:
            row.update(script='test_suite/a_book_staging_runner.py',reproduce_command='.venv/bin/python test_suite/a_book_staging_runner.py --confirm-staging-a-book '+source_arg)
            entries.append(dict(scope='Historical Copy Trading A-book routing',tc_id=row['tc_id'],status=row['status'],
                                script=row['script'],command=row['reproduce_command'],notes='Runs the A-book suite on the configured staging cohort; includes original-state restoration.'))
        ab_path.write_text(json.dumps(ab,indent=2))
    net_path=ROOT/'reports/netting_latest.json'
    if net_path.exists():
        net=json.loads(net_path.read_text())
        for row in net['cases']:
            if 'script' not in row:continue
            entries.append(dict(scope='Copy Trading netting / fresh accounts',tc_id=row['tc_id'],status=row['status'],
                                script=row['script'],command=row['reproduce_command'],notes='Only fresh-account manifest; MAM/PAMM rejected by the case selector.'))
    for name in ('copy_browser_latest.json','copy_access_latest.json','copy_scale_latest.json'):
        p=ROOT/'reports'/name
        if p.exists():
            for row in json.loads(p.read_text())['cases']:
                entries.append(dict(scope='Copy Trading completion',tc_id=row['tc_id'],status=row['status'],script=row['script'],command=row['reproduce_command'],notes=row['remarks']))
    # Earlier concurrency checks also have reusable scripts, not just command transcripts.
    entries += [
        dict(scope='Local concurrency',tc_id='RACE_001–008',status='PASS',script='tests/test_concurrency.py',
             command='.venv/bin/python -m pytest tests/test_concurrency.py -v',notes='Offline/mocked; no product trades.'),
        dict(scope='Earlier live race suite',tc_id='B1–B11',status='See archived evidence',script='test_suite/breakpoint_race_runner.py',
             command='.venv/bin/python test_suite/breakpoint_race_runner.py --end 6 --ramp 5,10,20 --i-understand-real-money',
             notes='Historical configured-cohort Copy Trading suite; uses test trades, cleanup, link changes and margin probes.'),
        dict(scope='Earlier race follow-up',tc_id='B1/B2/B7 follow-up',status='See archived evidence',script='scripts/staging_race_followup.py',
             command='.venv/bin/python scripts/staging_race_followup.py',notes='Historical configured cohort; .01-quantity follow-up and temporary follower funding.'),
        dict(scope='Earlier close accounting control',tc_id='B1 sequential/concurrent control',status='See archived evidence',script='scripts/staging_close_control.py',
             command='.venv/bin/python scripts/staging_close_control.py',notes='Historical configured follower1; compares one sequential close against20 concurrent close requests.'),
        dict(scope='Fresh fixture provisioning',tc_id='Fresh netting accounts',status='Provisioned',script='scripts/create_netting_test_accounts.py',
             command='.venv/bin/python scripts/create_netting_test_accounts.py --resume',notes='--resume fills missing roles in the retained manifest; without it a new fixture is created.'),
        dict(scope='Netting availability',tc_id='Netting preflight',status='See preflight evidence',script='scripts/check_netting_staging.py',
             command='.venv/bin/python scripts/check_netting_staging.py --fresh-accounts reports/netting_fresh_accounts.json',notes='Read-only after provisioning; does not run functional trades.'),
    ]
    payload=dict(scope='Every executed check has an existing source script. Planned manual/unexecuted cases are not claimed scripted or tested.',
                 current_scope='Copy Trading only; no MAM/PAMM product execution',entries=entries)
    (ROOT/'reports/reproduction_commands.json').write_text(json.dumps(payload,indent=2))
    esc=lambda x:html.escape(str(x))
    page='<!doctype html><html lang="en"><meta charset="utf-8"><title>Reproduction Scripts</title><style>body{font:14px system-ui;margin:24px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd4df;padding:9px;text-align:left;vertical-align:top}code{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>Scripts and Reproduction Commands</h1><p>'+esc(payload['scope'])+'</p><p>'+esc(payload['current_scope'])+'</p>'
    page+='<p>Run commands from the existing lpadmin repository with its installed dependencies and configured staging credentials. New netting commands require the explicit fresh-account manifest. Historical scripts retain their original configured-cohort scope. Source snapshots are in the package under automation/; .env and credentials are excluded.</p><table><tr><th>Scope</th><th>TC ID</th><th>Status</th><th>Script</th><th>Command</th><th>Notes</th></tr>'
    for row in entries:
        if not (ROOT/row['script']).is_file():raise RuntimeError('Missing reproduction script '+row['script'])
        page+='<tr>'+''.join('<td><code>'+esc(row[k])+'</code></td>' for k in ('scope','tc_id','status','script','command','notes'))+'</tr>'
    page+='</table></html>'
    (ROOT/'reports/reproduction_commands.html').write_text(page)
    print('Verified existing source files for',len(entries),'reproduction entries.')


if __name__=='__main__':main()
