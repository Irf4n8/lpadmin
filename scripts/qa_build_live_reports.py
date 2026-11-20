"""Build reports from recorded results. Never convert unexecuted scenarios to PASS."""
import csv
import html
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'reports/live_recheck_20261120'
DEEP=RUN/'deep_run'

# Cross-reference original requirements, preserving their unmet clauses.
COVERAGE={
 'F001':([], 'Existing authorized master verified; creation of a new master group and MT5/FIX binding were not performed.'),
 'F002':(['MAM-FEE-CONFIG'], 'Fee update/readback/restore tested; monthly crystallization and allocation-profile workflow not verified.'),
 'F004':(['MAM-UNFOLLOW-FLAT','MAM-JOIN-MIDTRADE'], 'API leave/rejoin tested; signed LPOA and Bound_Active rights-transfer workflow not verified.'),
 'F005':(['MARGIN-ISOLATION'], 'Zero-capital trade rejection tested; a configured minimum-balance JOIN threshold was not established.'),
 'F006':(['SIZE-BALANCE','SIZE-EQUITY'], 'Balance/equity sizing on current MAM tested; immutable configuration audit trail not inspected.'),
 'F007':(['MAM-MULTIPLIER-MIDTRADE','GUI-BALANCE-NEXT-ORDER'], 'Future-vs-existing sizing tested; original group allocation-profile transition differs from these follower settings.'),
 'F010':(['MAM-UNFOLLOW-FLAT'], 'Unfollow prevents new copies; LPOA revocation, Independent status and manager notification not verified.'),
 'F011':(['RACE-UNFOLLOW-OPEN-1','RACE-UNFOLLOW-OPEN-2','RACE-UNFOLLOW-OPEN-3'], 'Open/unfollow ordering observed; no contractual close-or-transfer selection workflow was established.'),
 'F014':(['ISOLATE-MANUAL-FOLLOWER'], 'Current platform permits independent follower trades. Original LPOA direct-trading lockout requirement is not demonstrated.'),
 'A001':(['SIZE-BALANCE'], 'Current MAM uses follower/master balance ratios. Original conserved block allocation across subaccounts is a different sizing model.'),
 'A002':(['SIZE-BALANCE'], 'Three balance ratios tested; original conserved 10/30/60 percent block allocation not demonstrated.'),
 'A003':(['SIZE-EQUITY'], 'Equity-ratio sizing tested with flat accounts; divergent floating-equity fixture not yet executed.'),
 'A006':(['SIZE-MULTIPLIERS'], 'BLACK:BTCUSD multiplier tiers and partial close tested across 100 followers; the exact 1.00-lot AUDUSD broker-routing fixture was not executed.'),
 'A009':(['SIZE-LOT-RULE-0.03-0.5','SIZE-LOT-RULE-0.01-1.5','SIZE-LOT-RULE-0.01-2.75'], 'Observed rounding to valid .01 entry steps; original .34999999 boundary fixture not executed.'),
 'A010':(['SIZE-LOT-RULE-0.01-0.25'], 'BLACK:BTCUSD multiplier-derived .0025 copy size clamps to .01. The original $100 proportional micro-account fixture is different and was not executed.'),
 'A013':(['RACE-GUI-BALANCE-ENTRY-1','RACE-GUI-BALANCE-ENTRY-2','RACE-GUI-BALANCE-ENTRY-3'], 'Cash-change/entry races tested; original floating-equity snapshot stress requires a separate oracle.'),
 'A014':(['LOAD-FIVE-BURST'], '500 child positions across 100 followers tested; not the specified single 100-lot block.'),
 'A015':(['SIZE-LOT-RULE-0.01-0.25','MARKET-BUY'], 'Small-ticket copy sizing tested; original conserved .10 block across ten accounts differs from current copy model.'),
 'R001':(['SIZE-LOT-RULE-0.03-0.5'], 'Copy-size rounding observed; conserved one-lot division across three accounts and remainder ledger not exercised.'),
 'R007':(['SIZE-MULTIPLIERS'], 'Exact multiplier products verified; block remainder-distribution model not exercised.'),
 'R008':(['SIZE-LOT-RULE-0.01-0.25'], 'Actual policy clamps below-minimum copies to .01; original remainder suppression policy is a separate requirement.'),
 'R014':(['LIFE-PARTIAL','SIZE-MULTIPLIERS'], 'Proportional remaining quantities tested; configured block-remainder policy not available for verification.'),
 'E001':(['MARKET-BUY','LOAD-FIVE-BURST'], '101-account fan-out verified; LP bridge delivery and original <50ms SLA not certified. Server timestamps reported separately.'),
 'E002':(['PENDING-100-FANOUT-LIMIT'], 'Pending ticket fan-out checked on BLACK:BTCUSD; original EURUSD price/allocation fixture replaced by user instruction.'),
 'E003':(['PENDING-TRIGGER-LIMIT-BUY','PENDING-TRIGGER-LIMIT-SELL'], 'Marketable limits fill/copy; natural resting-limit crossing, identical fills and simultaneity are not established by these cases.'),
 'E004':(['LIFE-PROTECTION-RETEST','RACE-INDEPENDENT-SL-TP'], 'Brackets and prices verified across 101 accounts; original <200ms SLA not certified.'),
 'E005':(['PENDING-100-FANOUT-LIMIT'], 'All-account pending ticket cancellation checked; see exact child-ticket evidence.'),
 'E006':(['LIVE-BRACKET-BUY','LIVE-BRACKET-SELL'], 'Natural bracket exits observed if triggered; a deliberately isolated single-child SL hit is a separate fixture.'),
 'E007':(['LIVE-BRACKET-BUY','LIVE-BRACKET-SELL'], 'Natural bracket exits observed if triggered; a deliberately isolated single-child TP hit is a separate fixture.'),
 'E008':(['LIFE-PARTIAL','SIZE-MULTIPLIERS','RACE-MULTI-REDUCE-1'], '50% child reduction and quantity conservation per position tested; original conserved block sizing differs.'),
 'E010':(['LOAD-FIVE-BURST','FINAL-FLAT'], 'Concurrent parent closes verified flat; UI Close All workflow and <1500ms SLA not certified.'),
 'E013':(['PENDING-100-FANOUT-STOP','PENDING-TRIGGER-STOP-BUY','PENDING-TRIGGER-STOP-SELL'], 'STOP entry/copy/cancel paths tested on BLACK:BTCUSD; see pending-ticket case for actual pre-trigger behavior.'),
 'P002':(['MARGIN-ISOLATION','RACE-MARGIN-RESERVATION-1'], 'Insufficient-margin follower isolation verified; master notification presentation not verified.'),
 'P006':(['ACCOUNTING-101'], 'Actual per-account fills and price PnL reconciled; configurable slippage-anomaly detection not verified.'),
 'P015':(['PENDING-100-FANOUT-LIMIT'], 'Pending cancellation/orphan state tested; injected LP child-submission failure not available.'),
 'M001':(['ACCOUNTING-101'], 'Current account terms inspected; differing leverage-tier mutation not executed.'),
 'M007':(['MARGIN-ISOLATION','RACE-MARGIN-RESERVATION-1','RACE-MARGIN-RESERVATION-2','RACE-MARGIN-RESERVATION-3'], 'Pre-entry margin enforcement and competing reservations verified; see exact observed terms.'),
 'M012':(['LIFE-HEDGE'], 'Long/short coexistence verified on real hedging; configured special hedging margin offsets not certified.'),
 'D001':(['BAL-OPEN-POSITION','GUI-BALANCE-NEXT-ORDER'], 'User-requested admin GUI cash update tested; original investor payment-deposit channel not exercised.'),
 'D002':(['BAL-WITHDRAW-HWM'], 'Admin cash reduction tested; investor withdrawal workflow not exercised.'),
 'D005':(['RACE-UNFOLLOW-OPEN-1'], 'Unfollow ordering observed; emergency LPOA market-close option not exposed/verified.'),
 'D007':(['MAM-UNFOLLOW-FLAT','MAM-JOIN-MIDTRADE'], 'Active roster changes tested; conserved block allocation redistribution is a different model.'),
 'D010':(['RACE-GUI-BALANCE-ENTRY-1'], 'One GUI cash change overlaps entry; five simultaneous cleared payment deposits not executed.'),
 'D011':(['GUI-BALANCE-NEXT-ORDER'], 'Doubling follower cash affects future sizing; institutional deposit channel not exercised.'),
 'H001':(['BAL-DEPOSIT-HWM','BAL-WITHDRAW-HWM'], 'Existing relationship benchmarks read and adjusted; independent initial HWM creation workflow not separately certified.'),
 'H002':(['FEE-HWM-POLICY-FIRST','FEE-HWM-POLICY-ABOVE','ACCOUNTING-101'], 'User-confirmed first-profit exemption and subsequent per-close share tested. Original monthly crystallization is not verified.'),
 'H006':(['ACCOUNTING-101'], 'Individual fee rows reconciled; simultaneous deliberately profitable/underwater contrast fixture not executed.'),
 'H008':(['BAL-DEPOSIT-HWM'], 'Dollar-for-dollar benchmark movement for admin credit verified; investor payment channel not exercised.'),
 'H009':(['BAL-WITHDRAW-HWM'], 'Current contract moves benchmark by cash delta; original proportional 50% HWM reduction is a different rule.'),
 'H010':(['ACCOUNTING-101','FEE-HWM-POLICY-ABOVE'], 'Fee rows and aggregate manager balance receipts checked; distinct designated-wallet routing not exercised.'),
 'H013':(['RACE-GUI-LEDGER-1','RACE-GUI-LEDGER-2','RACE-GUI-LEDGER-3'], 'Cash update/settlement/HWM races tested; retain fee evidence for whether positive manager share occurred.'),
 'C001':(['LOAD-FIVE-BURST'], 'Five orders x 100 followers = 500 child positions; not one order to 500 distinct followers.'),
 'C002':(['RACE-GUI-BALANCE-ENTRY-1','RACE-GUI-BALANCE-ENTRY-2','RACE-GUI-BALANCE-ENTRY-3'], 'GUI cash/entry overlaps tested; full deposit storm and internal snapshot isolation not instrumented.'),
 'C003':(['LIFE-PROTECTION-RETEST'], '101 accounts modified; original 500 distinct child-ticket population and SLA not exercised.'),
 'C004':(['RACE-UNFOLLOW-OPEN-1','RACE-MASTER-CHILD-CLOSE'], 'Related races tested; exact concurrent close/disconnect with contractual settlement policy still requires explicit verification.'),
 'C006':(['RACE-GUI-LEDGER-1','RACE-MARGIN-RESERVATION-1'], 'Observable ledger/margin invariants tested; database row-lock wait timing requires backend instrumentation.'),
 'C013':(['RACE-MULTI-REDUCE-1','RACE-MULTI-REDUCE-2','RACE-MULTI-REDUCE-3'], 'No over-close in repeated races; database lock ordering cannot be inferred from API outcomes.'),
 'O002':(['FINAL-FLAT'], 'Authorized account cleanup tested with trader APIs; admin forced-liquidation workflow not exercised.'),
 'O006':(['MAM-UNFOLLOW-FLAT'], 'Follower API unlink tested; administrator emergency unlink workflow not exercised.'),
 'O007':(['SETUP-BALANCE'], 'Actual Admin > Member > Real Hedging > Set balance verified for 101 accounts; treasury debit/immutable audit not certified.'),
 'O009':(['ACCOUNTING-101'], 'Account-level reconciliation performed; external clearing LP/EOD reconciliation not accessible on this B-book run.'),
 'O011':(['LIFE-FOLLOWER-CLOSE'], 'Individual follower close tested; separate administrator force-close privilege path not exercised.'),
 'O012':(['GUI-MASTER-CASH-ISOLATION'], 'Master cash change isolation tested; personal-account loss and legal custody separation not certified.'),
}

MODULE_BLOCKERS={
 'F':'LPOA contracts, independent group-management/archival controls or required role fixtures are not available in the verified API/UI flow.',
 'A':'The specified allocation policy/currency/conserved-block fixture is not represented by the tested multiplier/balance/equity copy model.',
 'R':'No configurable remainder-distribution ledger, rebate ledger, or exact block-allocation policy was available for this requirement.',
 'E':'This exact execution/terminal/event-ordering fixture was not available or not executed; related market cases do not prove it.',
 'P':'Requires LP partial-fill, depth, rejection, or routing fault injection; these dedicated accounts are B-book and no LP simulator was supplied.',
 'M':'Requires configured stop-out/leverage/news/swap/notification fixtures beyond the verified account margin cases.',
 'D':'Requires investor payment/withdrawal, lockup, reversal, or emergency LPOA workflow. Admin Set balance is not a substitute.',
 'H':'Requires time-controlled fee cycles, HWM recovery history, management fees, tax/rebate/statement configuration not available in this run.',
 'C':'Requires infrastructure hooks, a different account population, distributed nodes, gateway idempotency contract, or long-duration load tooling not supplied.',
 'L':'Requires compliance policy fixtures, jurisdiction controls, document/audit access and authorized evidence. Trading API success cannot establish compliance.',
 'O':'Requires operator/backoffice infrastructure, deployment/failover controls, immutable logs, or external clearing evidence not supplied.',
}


def main():
    raw=[]
    for p in sorted(DEEP.glob('results_*.json')):
        for r in json.loads(p.read_text(encoding='utf-8')):
            r['result_file']=str(p.relative_to(ROOT)).replace('\\','/')
            compressed=DEEP/(r['trace']+'.gz')
            if compressed.exists():r['trace']=compressed.name
            raw.append(r)
    latest={r['id']:r for r in raw}
    corrections=[]
    excluded=set()
    if latest.get('LIFE-PROTECTION-RETEST',{}).get('status')=='PASS':
        excluded.add('LIFE-PROTECTION')
        corrections.append('Initial LIFE-PROTECTION failure was a test-oracle error: child brackets link by market_order_id. Corrected all-account set/remove/price check passed. Raw failure retained.')
    if latest.get('FINAL-FLAT',{}).get('status')=='PASS':
        excluded.add('SETUP-CLEAN')
        corrections.append('Initial SETUP-CLEAN verification was blocked by a transient failed read. Subsequent all-account flat checks passed. The original blocked attempt remains in raw evidence.')
    if all(latest.get(k,{}).get('status')=='PASS' for k in ('FEE-HWM-POLICY-FIRST','FEE-HWM-POLICY-ABOVE')):
        excluded.update(('FEE-LIVE-PROFIT','FEE-HWM-FIRST-REPRO','FEE-HWM-ABOVE-CONTROL'))
        corrections.append('The original fee assertion wrongly expected a manager share on the first profitable benchmark crossing. The user explicitly confirmed that first profit is exempt and only subsequent profit with balance already above the benchmark is shared. Both corrected live cases were rerun, including exact share, split conservation, brokerage and balance reconciliation. Earlier failures and the weaker control remain in raw evidence; no platform fee defect is claimed.')
    for id_ in ('LIVE-BRACKET-SELL','FEE-LIVE-PROFIT'):
        if latest.get(id_,{}).get('status')=='PASS' and any(r['id']==id_ and r['status']=='BLOCKED' for r in raw):
            corrections.append(f'{id_}: an earlier attempt could not obtain its live-market fixture within the observation window. A later recorded attempt passed; the blocked attempt is preserved, not deleted.')
    corrections.append('Lot-rule assertions were strengthened and rerun: exactly one child with the specified rounded quantity is required, and other accounts are checked. Earlier valid-step-only checks were insufficient to prove copying.')
    validated=[r for k,r in latest.items() if k not in excluded]
    counts=dict(Counter(r['status'] for r in validated))
    scenarios=json.loads((ROOT/'scratch/all_165_scenarios.json').read_text(encoding='utf-8'))
    matrix=[]
    for sc in scenarios:
        suffix=sc['id'].split('-')[1]
        refs,note=COVERAGE.get(suffix,([],MODULE_BLOCKERS[suffix[0]]))
        linked=[latest[x] for x in refs if x in latest]
        status='PARTIAL' if any(r['status']=='PASS' for r in linked) else 'BLOCKED'
        if any(r['status']=='FAIL' for r in linked):status='FAIL_RELATED'
        row={**sc,'test_case_id':sc['id'],'status':status,'coverage_note':note,
             'executed_check_ids':[r['id'] for r in linked],
             'evidence_files':sorted({r['result_file'] for r in linked}),
             'release_signoff':False}
        matrix.append(row)
    matrix_counts=dict(Counter(r['status'] for r in matrix))
    summary={'generated_at':datetime.now(timezone.utc).isoformat(),'release_signoff':False,
             'scope':{'instance':'real','mode':'hedging','symbol':'BLACK:BTCUSD','master':'mamm@mailinator.com','followers':100,
                      'funds':'User confirmed dedicated simulated test funds despite real-money labels'},
             'live_check_totals':counts,'raw_attempts':len(raw),'unique_validated_checks':len(validated),
             'original_165_coverage':matrix_counts,'corrections':corrections,'results':validated,'original_scenarios':matrix}
    final_path=DEEP/'final_account_state.json'
    if final_path.exists():
        final=json.loads(final_path.read_text(encoding='utf-8'))
        summary['final_state']={'recorded_at':final['time'],'accounts':len(final['positions']),
            'open_positions':sum(d['count'] for d in final['positions'].values()),
            'working_orders':sum(len(v) for v in final['working_orders'].values()),
            'balances':sorted({d['funds']['balance'] for d in final['positions'].values()}),
            'evidence_file':str(final_path.relative_to(ROOT)).replace('\\','/')}
    (RUN/'validated_results.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    with (RUN/'validated_checks.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=['id','name','status','started_at','finished_at','result_file','trace']);w.writeheader()
        for r in validated:w.writerow({k:r.get(k) for k in w.fieldnames})
    with (RUN/'mam_165_execution_inventory.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=['test_case_id','title','status','coverage_note','executed_check_ids']);w.writeheader()
        for r in matrix:w.writerow({k:r.get(k) for k in w.fieldnames})
    (RUN/'mam_165_execution_inventory.json').write_text(json.dumps(matrix,indent=2),encoding='utf-8')
    lines=['# MAM live QA report — 20 November 2026','',
        '**Release decision: NOT SIGNED OFF.** Executed checks and original-plan coverage are separate. No claim of 165/165 completion or production readiness is made.','',
        f"Live checks: **{counts}** across {len(validated)} unique check IDs (includes repeated race trials). Raw attempts: {len(raw)}.",
        f"Original 165 scenarios: **{matrix_counts}**. PARTIAL is not PASS. The executed BLACK:BTCUSD cases are separately identified below; related checks do not prove every clause of the old plan.",'',
        'Scope: dedicated test master mamm@mailinator.com and mamf1–mamf100@mailinator.com; real hedging only; BLACK:BTCUSD. No paper/netting trading was tested.','',
        'All 101 balances were set to 1,000,000 through actual Playwright Admin → People → Members → member → Real (Hedging) → Set balance, then verified through API reads. Later cases deliberately varied balances and MAM terms. Final account snapshots describe the actual ending state.','',
        '## Findings and report integrity','']
    failures=[r for r in validated if r['status']=='FAIL']
    if failures:
        for r in failures:lines.append(f"- **{r['id']} — {r['name']}**: FAIL in recorded assertion. Read evidence and diagnosis before classifying a platform defect: `{r['result_file']}`.")
    else:lines.append('- No platform defect has been confirmed by the validated live assertions in this report. Passing tests do not establish correctness outside their stated scope.')
    lines+=['- The separate offline harness audit still reproduces 10 failed checks. These are tooling defects, not 10 newly observed platform defects.',
        '- Historical reports were archived before rewriting in `reports/live_recheck_20261120/historical_reports_before_rewrite.zip`.',
        '- Initial read-only relationship states changed between snapshots before the exclusive test window. No stable platform defect was established from that observation.',
        '- Original requirements include LP routing, fixed-percentage/conserved-block allocation, 500/1000 distinct followers, database locks, failover, time-based fees, and compliance controls. Those are not certified by a B-book 100-follower API/UI run.','']
    lines+=['## Verified behavior and limits','',
        '- BUY/SELL market copying, simultaneous hedged sides, partial/full close, independent follower trades, SL/TP propagation and natural TP exits were exercised.',
        '- Resting LIMIT/STOP tickets were inspected across all 101 accounts and cancelled; marketable pending orders were triggered. These are distinct from an injected gap/slippage test.',
        '- Multiplier, balance and flat-account equity sizing, entry lot rounding, invalid inputs and cross-account position access were checked.',
        '- Repeated close/close, partial/full-close, multiple-reduction, pending modify/cancel, follow/entry, margin-reservation, independent bracket edit, GUI cash/entry and GUI cash/settlement races were exercised.',
        '- Five concurrent master entries created 500 child positions across 100 followers. This does not establish support for 500 distinct followers.',
        '- Per-account settlement, brokerage, recorded manager-share rows and cash-delta/HWM reconciliation were checked. First-profit exemption and subsequent positive fee coverage are governed by the FEE-HWM-POLICY cases below.',
        '- 323 earlier read-only assertions passed: 23 endpoint/auth/account-set checks plus three per follower. These are separate from the live check count.',
        '- Network capture provides observable HTTP evidence; no backend source, database access, broker fault-injection controls or time-control hooks were available.',
        '- GUI/API races establish observed overlapping requests and allowed outcomes, not exact server simultaneity or exhaustive coverage of every interleaving.','',
        '## Confirmed defects in the supplied test tooling','',
        'The offline regression run reproduced **25 PASS / 10 FAIL**. No fixes to the original application/test-client implementation were made. Full reproductions and source locations are in `reports/QA_REVIEW_20261120.txt` and `reports/qa_retest_20261120.json`.','',
        '| ID | Severity | Reproduced problem |','|---|---|---|',
        '| QA-01 | High | F003 reports PASS after both required API calls return 503. |',
        '| QA-02 | High | Local arithmetic with zero platform calls receives a production-ready label. |',
        '| QA-03 | High | Bulk close reports an empty successful cleanup after inventory read failure. |',
        '| QA-04 | High | Bulk cancellation reports success after order inventory read failure. |',
        '| QA-05 | High | Full-close scenario passes when close and verification requests fail. |',
        '| QA-06 | Medium | Authentication reports success without a usable chart token. |',
        '| QA-07 | High | An ambiguous timed-out order POST is automatically replayed without an idempotency guarantee; duplicate execution risk, not a reproduced live duplicate. |',
        '| QA-08 | Medium | Dashboard command validation accepts infinite lot size. |',
        '| QA-09 | Medium | Reversed follower range raises IndexError instead of validation. |',
        '| QA-10 | Medium | Malformed test-operation parameters raise AttributeError instead of returning 400. |','']
    if 'final_state' in summary:
        state=summary['final_state']
        lines+=['## Final account state','',f"Recorded {state['recorded_at']}: {state['accounts']} accounts, {state['open_positions']} open positions, {state['working_orders']} working orders, observed balance values {state['balances']}. Final relationship validation is recorded in FINAL-ACCOUNT-STATE.",'',
            'All final cash resets used the actual Admin Member Set balance GUI. The master fee setting is recorded in the final check; the additional mamf4 relationship removed for isolation remains ended. Historic trades and cash adjustments remain in account history.','']
    blocked=[r for r in validated if r['status']=='BLOCKED']
    if blocked:
        lines+=['## Blocked live checks','']+[f"- **{r['id']}**: {r['details'].get('error','See recorded details')}" for r in blocked]+['']
    lines+=['## Corrected assertions and reruns','']+[f'- {s}' for s in corrections]+['',
        '## Executed checks','', '| ID | Result | Check | Evidence |','|---|---|---|---|']
    for r in validated:lines.append(f"| {r['id']} | {r['status']} | {r['name']} | `{r['result_file']}`; `{r['trace']}` |")
    lines+=['','## Original 165-case traceability','',
        '| Original ID | Coverage | Requirement | Executed checks / remaining gap |','|---|---|---|---|']
    for r in matrix:lines.append(f"| {r['test_case_id']} | {r['status']} | {r['title']} | {', '.join(r['executed_check_ids']) or 'None'} — {r['coverage_note']} |")
    lines+=['','## Evidence and reproducibility','',
        '- `scripts/qa_mam_live.py` and `scripts/qa_mam_additional.py`: authorized mutating live probes. Do not rerun against production funds.',
        '- `reports/live_recheck_20261120/deep_run/results_*.json`: original timestamped attempts and detailed assertions.',
        '- `reports/live_recheck_20261120/deep_run/http_*.jsonl.gz`: request/response evidence without bearer tokens or passwords; gzip JSON Lines.',
        '- `reports/live_recheck_20261120/deep_run/ui_*.png`: real admin GUI balance updates.',
        '- `reports/live_recheck_20261120/deep_run/observed_fanout_latency.json`: server opened_at differences; not browser delivery or LP latency.',
        '- `reports/live_recheck_20261120/validated_checks.csv` and `mam_165_execution_inventory.csv`: machine-readable results and explicit gaps.','']
    report='\n'.join(lines)
    (ROOT/'MAM_QA_MASTER_TEST_EXECUTION_REPORT.md').write_text(report,encoding='utf-8')
    (ROOT/'mam_test_execution_reports/MAM_MASTER_EXECUTIVE_SUMMARY.md').write_text(report,encoding='utf-8')
    (ROOT/'mam_test_execution_reports/MAM_MASTER_SUMMARY.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    for row in matrix:
        (ROOT/f"mam_test_execution_reports/individual_reports/{row['test_case_id']}.json").write_text(json.dumps(row,indent=2),encoding='utf-8')
    for idx,p in enumerate(sorted((ROOT/'mam_test_execution_reports/markdown_reports').glob('MODULE_*.md'))):
        module=sorted({s['module'] for s in matrix},key=lambda x:int(x.split(':')[0].split()[-1]))[idx]
        entries=[r for r in matrix if r['module']==module]
        text=f'# {module}\n\nRewritten from live evidence. No release sign-off.\n\n'
        for r in entries:text+=f"## {r['test_case_id']} — {r['title']}\n\nStatus: **{r['status']}**\n\n{r['coverage_note']}\n\nEvidence checks: {', '.join(r['executed_check_ids']) or 'None; blocked'}\n\n"
        p.write_text(text,encoding='utf-8')
    races=[r for r in validated if 'RACE' in r['id'] or 'BURST' in r['id']]
    race_report='# MAM race-condition execution report\n\nReal hedging / BLACK:BTCUSD / dedicated simulated accounts. No production sign-off.\n\n'
    for r in races:race_report+=f"- **{r['status']} {r['id']}** — {r['name']}; evidence `{r['result_file']}`.\n"
    race_report+='\nThread-barrier races and GUI/API overlapping operations were observed; exact server simultaneity and all possible interleavings are not claimed.\n'
    (ROOT/'MAM_RACE_CONDITIONS_AND_TEST_SCENARIOS_REPORT.md').write_text(race_report,encoding='utf-8')
    # Replace legacy prose report claims, while preserving their exact originals in the archive.
    manifest=json.loads((RUN/'historical_report_manifest.json').read_text(encoding='utf-8'))
    (RUN/'historical_report_status.json').write_text(json.dumps({
        'status':'SUPERSEDED_AS_RELEASE_EVIDENCE',
        'archive':'historical_reports_before_rewrite.zip',
        'current_report':'../../MAM_QA_MASTER_TEST_EXECUTION_REPORT.md',
        'note':'Old raw JSON evidence remains historical; old prose reports and the original 165-case reports were rewritten. The separate qa_retest tooling audit remains current.',
        'archived_files':manifest},indent=2),encoding='utf-8')
    for rel in manifest:
        p=ROOT/rel
        if p.suffix=='.md' and 'mam_test_execution_reports' not in p.parts and p.name not in ('MAM_QA_MASTER_TEST_EXECUTION_REPORT.md','MAM_RACE_CONDITIONS_AND_TEST_SCENARIOS_REPORT.md'):
            p.write_text('# Superseded QA report\n\nThis report was replaced on 20 November 2026 after assertion review and live real-hedging retesting. Its old pass/fail counts are not current release evidence.\n\nSee `MAM_QA_MASTER_TEST_EXECUTION_REPORT.md` and `reports/live_recheck_20261120/validated_results.json` for current results, detailed evidence, and blocked cases.\n\nThe exact prior report is preserved in `reports/live_recheck_20261120/historical_reports_before_rewrite.zip`. No old result has been silently promoted to PASS.\n',encoding='utf-8')
    htmlrows=''.join(f"<tr><td>{html.escape(r['id'])}</td><td>{r['status']}</td><td>{html.escape(r['name'])}</td><td><a href='deep_run/{Path(r['result_file']).name}'>Assertion evidence</a> / <a href='deep_run/{r['trace']}'>HTTP trace</a></td></tr>" for r in validated)
    page=f'''<!doctype html><meta charset="utf-8"><title>MAM QA live results</title><style>body{{font:16px system-ui;max-width:1200px;margin:40px auto;padding:20px;color:#182536}}table{{border-collapse:collapse;width:100%}}td,th{{padding:10px;border-bottom:1px solid #ddd;text-align:left}}.warning{{background:#fff0ce;padding:20px}}input{{padding:12px;width:90%}}</style><h1>MAM live QA — 20 November 2026</h1><p class="warning">NOT SIGNED OFF FOR PRODUCTION. Original 165-case coverage includes explicit partial and blocked requirements.</p><p>{html.escape(str(counts))} — {len(validated)} unique live checks, including repeated race trials.</p><p>Real hedging · BLACK:BTCUSD · 1 master + 100 dedicated test followers</p><p>Original 165 coverage: {html.escape(str(matrix_counts))}</p><p><a href="validated_results.json">Detailed JSON evidence index</a> · <a href="validated_checks.csv">Live-check CSV</a> · <a href="mam_165_execution_inventory.csv">Original 165 coverage</a></p><input id="filter" placeholder="Filter checks" oninput="document.querySelectorAll('tbody tr').forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(this.value.toLowerCase()))"><table><thead><tr><th>ID</th><th>Result</th><th>Check</th></tr></thead><tbody>{htmlrows}</tbody></table>'''
    page=page.replace('<th>Check</th>', '<th>Check</th><th>Evidence</th>')
    page=page.replace('<input id="filter"', '<p><a href="../../MAM_QA_MASTER_TEST_EXECUTION_REPORT.md">Complete report and coverage gaps</a> · <a href="../QA_REVIEW_20261120.txt">10 reproduced tooling defects</a> · <a href="confirmed_fee_policy.json">User-confirmed fee policy</a></p><input id="filter"')
    (RUN/'REPORT.html').write_text(page,encoding='utf-8')
    state=summary.get('final_state',{})
    status_text=(f"LIVE MAM RETEST COMPLETED FOR THE EXECUTED SCOPE — NOT A RELEASE SIGN-OFF\n"
        f"Generated: {summary['generated_at']}\n"
        f"Real hedging only; BLACK:BTCUSD; dedicated simulated accounts confirmed by user.\n"
        f"Unique validated live checks: {len(validated)}; results: {counts}.\n"
        f"Raw attempts retained: {len(raw)}. Corrected assertions are disclosed in the main report.\n"
        f"Separate read-only checks: 323 PASS. Separate offline audit: 25 PASS, 10 FAIL.\n"
        f"Original 165-case coverage: {matrix_counts}; partial and blocked are not passes.\n"
        f"Final account state: {json.dumps(state)}\n"
        "All 100 target follower links were checked in FINAL-ACCOUNT-STATE. GUI cash resets and original modified settings are recorded.\n"
        "The user authorized trading, cleanup and cash/configuration changes and confirmed an exclusive test window.\n"
        "No backend/database/fault-injection/time-control access is available. Such requirements remain unverified.\n"
        "Current report: ../../MAM_QA_MASTER_TEST_EXECUTION_REPORT.md\n"
        "Browsable index: REPORT.html\n"
        "Detailed evidence: validated_results.json and deep_run/results_*.json\n"
        "Prior reports: historical_reports_before_rewrite.zip\n")
    (RUN/'CURRENT_STATUS.txt').write_text(status_text,encoding='utf-8')
    print(json.dumps({'validated_checks':len(validated),'totals':counts,'original_165':matrix_counts,'raw_attempts':len(raw)},indent=2))


if __name__=='__main__':main()
