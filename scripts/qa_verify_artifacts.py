"""Verify report counts, evidence links and final recorded account state offline."""
import ast
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'reports/live_recheck_20261120'
DEEP=RUN/'deep_run'
summary=json.loads((RUN/'validated_results.json').read_text(encoding='utf-8'))
rows=summary['results']
assert len(rows)==len({r['id'] for r in rows})==summary['unique_validated_checks']
assert dict(Counter(r['status'] for r in rows))==summary['live_check_totals']
assert summary['release_signoff'] is False
for row in rows:
    raw=json.loads((ROOT/row['result_file']).read_text(encoding='utf-8'))
    assert any(r['id']==row['id'] and r['status']==row['status'] and r['details']==row['details'] for r in raw),row['id']
    assert (DEEP/row['trace']).is_file(),row['trace']
matrix=summary['original_scenarios']
assert len(matrix)==len({r['test_case_id'] for r in matrix})==165
assert dict(Counter(r['status'] for r in matrix))==summary['original_165_coverage']
assert all(r['status']!='PASS' and r['release_signoff'] is False for r in matrix)
with (RUN/'mam_165_execution_inventory.csv').open(encoding='utf-8',newline='') as f:
    assert len(list(csv.DictReader(f)))==165
for r in matrix:
    individual=json.loads((ROOT/f"mam_test_execution_reports/individual_reports/{r['test_case_id']}.json").read_text(encoding='utf-8'))
    assert individual==r
final=json.loads((DEEP/'final_account_state.json').read_text(encoding='utf-8'))
assert len(final['positions'])==101
assert all(v['count']==0 and abs(v['funds']['balance']-1000000)<.01 for v in final['positions'].values())
assert sum(map(len,final['working_orders'].values()))==0
master=final['relationships']['mamm@mailinator.com']
active=[r for r in master['followers'] if r['status']=='active']
assert len(active)==100 and len({r['follower_client_id'] for r in active})==100
assert master['master']['share_percent']==50
for email,links in final['relationships'].items():
    if email=='mamm@mailinator.com':continue
    target=[r for r in links['following'] if r['master_client_id']=='mem_11434b0b9d9d210899' and r['status']=='active']
    assert len(target)==1 and target[0]['method']=='multiplier' and target[0]['multiplier']==1
for name in ['qa_mam_live.py','qa_mam_additional.py','qa_build_live_reports.py','qa_live_readonly_recheck.py']:
    ast.parse((ROOT/'scripts'/name).read_text(encoding='utf-8'))
result={'status':'PASS','unique_live_checks':len(rows),'live_totals':summary['live_check_totals'],
        'original_cases':165,'all_evidence_links_verified':True,'raw_assertions_preserved':True,
        'final_accounts':101,'active_target_followers':100,'open_positions':0,'working_orders':0,
        'balance_each':1000000,'master_share_percent':50,'follower_method':'multiplier','multiplier':1}
(RUN/'report_integrity_verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
