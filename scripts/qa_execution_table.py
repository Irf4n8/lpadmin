"""Format recorded QA evidence; never execute trades or infer additional passes."""
import csv
import json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'reports/live_recheck_20261120'
data=json.loads((RUN/'validated_results.json').read_text(encoding='utf-8'))
offline=json.loads((ROOT/'reports/qa_retest_20261120.json').read_text(encoding='utf-8'))
HEAD=['TC ID','Test Case Description','Pre-Conditions','Test Steps','Test Data','Expected Result','Actual Result','Status','Severity','Defect ID','Remarks']

def compact(value,depth=0):
    if isinstance(value,dict):
        if not value:return '{}'
        if depth>=2:return f'{len(value)} recorded fields'
        items=list(value.items())
        return '; '.join(str(k)+'='+compact(v,depth+1) for k,v in items[:8])+(' (additional fields in evidence)' if len(items)>8 else '')
    if isinstance(value,list):
        if not value:return '[]'
        if depth>=2:return f'{len(value)} recorded entries'
        return '['+'; '.join(compact(x,depth+1) for x in value[:2])+(' ; ...' if len(value)>2 else '')+f'] ({len(value)} entries)'
    return str(value)

def steps(id_):
    # Operation summaries, not a substitute for exact recorded requests/source.
    if id_.startswith('SETUP'):return '1. Open Admin > Members > member > Real (Hedging).\n2. Set balance through the UI.\n3. Read back each scoped account.'
    if id_.startswith('FINAL'):return '1. Close remaining scoped positions and cancel working orders.\n2. Restore follower configuration; reset GUI balances where specified.\n3. Read back the final inventory and account state.'
    if id_.startswith('FEE-'):return '1. Establish the required pre-trade benchmark relationship.\n2. Open hedged market positions and close a profitable side.\n3. Compare recorded share, brokerage and resulting balance with the confirmed fee rule.\n4. Clean up remaining positions.'
    if id_.startswith('SIZE'):return '1. Configure the stated multiplier or allocation method and balances.\n2. Submit a master entry.\n3. Inspect follower quantities; reduce where the case specifies.\n4. Close positions and verify cleanup.'
    if id_.startswith('VALID'):return '1. Submit the case-specific invalid order request.\n2. Inspect rejection response.\n3. Verify no unexpected positions.'
    if id_.startswith('AUTH'):return '1. Open a master position.\n2. Attempt follower access to master close, reduction and protection operations.\n3. Verify rejection and intact master position.\n4. Clean up.'
    if id_.startswith('RACE'):return '1. Establish the position, order or relationship fixture named in this case.\n2. Submit the named operations concurrently, using UI submission for cash changes.\n3. Read responses and resulting position/order/ledger state.\n4. Check the case-specific invariants and clean up.'
    if id_.startswith('PENDING'):return '1. Submit the stated pending order.\n2. Inspect pending tickets or trigger the marketable order, as named.\n3. Inspect copied state.\n4. Cancel or close and verify the resulting inventory.'
    if id_.startswith(('GUI','BAL-')):return '1. Establish the stated open-trade or cash fixture.\n2. Change the relevant balance through Admin > Members > Set balance.\n3. Inspect positions, sizing or benchmark as named.\n4. Close test positions and restore configuration.'
    if id_=='ACCOUNTING-101':return '1. Snapshot funds and account terms.\n2. Open and close a copied master trade.\n3. Read history and fee rows.\n4. Reconcile price PnL, brokerage, shares, balances and released margin across 101 accounts.'
    if id_.startswith('LOAD'):return '1. Submit five concurrent master entries.\n2. Inspect five positions per follower.\n3. Close the parents concurrently.\n4. Verify no remaining positions.'
    if id_.startswith('MAM-'):return '1. Snapshot the relevant MAM relationship/configuration.\n2. Perform the role, follow/unfollow or configuration action named in the case.\n3. Read back the relationship and, where applicable, subsequent trade copies.\n4. Restore the tested configuration.'
    if id_.startswith('LIVE-BRACKET'):return '1. Open the stated market side and inspect copied positions.\n2. Place protection around the current market.\n3. Observe a natural exit within the test window.\n4. Inspect one closing history row per position and verify no orphans.'
    if id_=='MARGIN-ISOLATION':return '1. Set one follower balance to zero using the admin GUI.\n2. Open a master trade.\n3. Verify that follower is excluded while other followers copy.\n4. Close and restore the balance.'
    return '1. Open the case-specific master/follower position fixture.\n2. Perform the close, reduction, protection or independent-trade action named in this case.\n3. Inspect all affected positions/orders.\n4. Close remaining test positions.'

def actual(details):
    priority=['error','expected','actual','expected_child_quantity','child_positions','expected_manager_share','shares',
              'expected_balance','actual_balance','expected_hwm','actual_hwm','expected_hwm','master_history',
              'positions_remaining','accounts_checked','accounts_verified','balance_each','working_order_count',
              'master_intact','relationship_unchanged','reduce','response','final_order','history_rows_per_account']
    selected={k:details[k] for k in dict.fromkeys(priority) if k in details}
    for k,v in details.items():
        if any(s in k for s in ['error','incorrect','unexpected','orphans','still_working','lost_updates']):selected[k]=v
    if not selected:selected=details
    return compact(selected)

def testdata(r):
    d=r['details']; selected={k:d[k] for k in ['master_qty','multiplier','unrounded_product','expected_child_quantity','balance_each','accounts'] if k in d}
    if 'ui' in d:selected['GUI target']=d['ui'].get('value')
    if r['id'].startswith('FEE'):selected.update(share_percent=d['relationship']['share_percent'],benchmark=d['relationship']['starting_balance'],before_balance=d['balance_before_entry']['balance'])
    return 'Real hedging; BLACK:BTCUSD; authorized master/follower test accounts. '+(compact(selected) if selected else 'Exact payloads and account selection: linked HTTP evidence.')

def cell(v):return str(v).replace('&','&amp;').replace('|','&#124;').replace('\r','').replace('\n','<br>')
def table(rows):
    return '\n'.join(['| '+' | '.join(HEAD)+' |','| '+ ' | '.join([':---']*7+[':---:']*3+[':---'])+' |']+['| '+' | '.join(cell(x) for x in row)+' |' for row in rows])
def save_csv(name,rows):
    with (RUN/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(HEAD);w.writerows(rows)

live=[]
for r in data['results']:
    d=r['details']
    expected=d.get('assertion') or d.get('allowed_outcomes') or r['name']
    remark=f"Executed {r['started_at']}. Evidence: {r['result_file']}; HTTP: reports/live_recheck_20261120/deep_run/{r['trace']}."
    if d.get('scope'):remark+=' Scope: '+str(d['scope'])
    if d.get('oracle'):remark+=' Oracle: '+str(d['oracle'])
    live.append([r['id'],r['name'],'Dedicated simulated accounts; authenticated real-hedging sessions; case-specific state established by the runner.',steps(r['id']),testdata(r),expected,actual(d),r['status'],'—','—',remark])

original=[]
current={r['id']:r for r in data['results']}
for r in data['original_scenarios']:
    refs=r['executed_check_ids']
    observed='; '.join(k+': '+current[k]['status'] for k in refs if k in current)
    original.append([r['test_case_id'],r['title'],r['precondition'],r['steps'],
        'Original scenario data is specified in preconditions/steps. Related live checks use BLACK:BTCUSD.',
        r['expected'],('Related checks: '+observed+'. ' if observed else 'No completed execution of this original condition. ')+r['coverage_note'],
        r['status'],'—','—',f"{r['module']}; original priority {r['priority']} (not defect severity). {r['coverage_note']}"])

local=[]; defect_number=0
for i,r in enumerate(offline['results'],1):
    defect='—';severity='—'
    if r['status']=='FAIL':
        defect_number+=1;defect=f'QA-{defect_number:02}'
        severity='High' if defect_number in (1,2,3,4,5,7) else 'Medium'
    local.append([f'OFFLINE-{i:03}',r['name'],'Repository and Python dependencies available; outbound sockets blocked by the audit runner.',
        f"1. Run python reports/qa_retest_20261120.py.\n2. Inspect the named check: {r['name']}.\n3. Compare actual and expected results.",
        'Controlled offline inputs/mocks from reports/qa_retest_20261120.py; no live trading.',compact(r['expected']),compact(r['actual']),r['status'],severity,defect,
        'Evidence: reports/qa_retest_20261120.json. Reproduction and source locations: reports/QA_REVIEW_20261120.txt. This result concerns supplied tooling, not remote-platform behavior.'])

attempts=[]
for p in sorted((RUN/'deep_run').glob('results_*.json')):
    for r in json.loads(p.read_text(encoding='utf-8')):
        chosen=current.get(r['id'])
        is_current=chosen and chosen['started_at']==r['started_at'] and Path(chosen['result_file']).name==p.name
        if is_current:continue
        attempts.append([r['id'],r['name'],'Historical attempt; see its recorded fixture.','See the timestamped source/evidence for this attempt.',
            'Original inputs retained in HTTP trace.',r['details'].get('assertion',r['name']),actual(r['details']),r['status'],'—','—',
            f"Historical/superseded attempt; not counted as a current pass. {r['started_at']}; deep_run/{p.name}. See correction log below."])

text=['# MAM Test Case Execution Report','',
      '## 1. Execution Summary','',
      '**No, every test condition is not complete. No production sign-off is issued.**','',
      '- 81 validated live checks: 81 PASS. These include setup/final-state checks and repeated race trials; they are not 81 completed cases from the original 165-case plan.',
      '- Original 165-case plan: 62 PARTIAL and 103 BLOCKED/unexecuted. None is represented as fully completed by the current mapping.',
      '- Separate offline audit: 35 checks, 25 PASS and 10 FAIL. The ten defect IDs below refer to reproduced tooling defects.',
      '- 96 live attempts are retained. The 15 historical/superseded attempts are listed separately with their original statuses.',
      '- This document reformats existing evidence; no new live tests were executed during this formatting step.',
      '- PARTIAL is retained as an explicit status because a related passing check does not satisfy every clause of the original case. BLOCKED is the existing inventory label and includes unexecuted conditions; it does not establish that all such conditions are technically impossible.',
      '- Severity is assigned only to confirmed defects. Original case priority is shown in Remarks and is not presented as defect severity.',
      '- Credentials are omitted. Detailed request payloads, account selections and responses remain in the referenced evidence. Steps in the live table are operation summaries; exact reproduction is in the retained runner and traces.','',
      '## 2. Test Case Execution Table (Main Section)','',table(live),'',
      '## 3. Original 165 Test Conditions — Completion and Gaps','',table(original),'',
      '## 4. Offline Test-Tooling Checks and Confirmed Defects','',table(local),'',
      '## 5. Historical Attempts — Original Results Preserved','',table(attempts),'',
      '## 6. Assertion Corrections','']
text += ['- '+s for s in data['corrections']]
text += ['', '## 7. Final Recorded Account State','',
         f"As recorded at {data['final_state']['recorded_at']}: 101 balances at 1,000,000, zero open positions, zero working orders, and 100 active target followers at multiplier 1. These are the ending observations from the prior execution, not a new live snapshot.",'']
dest=ROOT/'MAM_TEST_CASE_EXECUTION_TABLE.md'
dest.write_text('\n'.join(text),encoding='utf-8')
for name,rows in [('live_execution_table.csv',live),('original_165_execution_table.csv',original),('offline_execution_table.csv',local),('historical_attempts_table.csv',attempts)]:save_csv(name,rows)
assert len(live)==81 and len(original)==165 and len(local)==35 and len(attempts)==15 and defect_number==10
assert all(len(r)==len(HEAD) for rows in (live,original,local,attempts) for r in rows)
print(json.dumps({'report':str(dest),'columns':HEAD,'live_rows':len(live),'original_rows':len(original),'offline_rows':len(local),'historical_rows':len(attempts),'original_statuses':dict(Counter(r[7] for r in original))},indent=2))
