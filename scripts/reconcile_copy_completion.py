"""Attach new observations without promoting limited checks to full master-spec passes."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 path=ROOT/'reports/master_spec_latest.json';report=json.loads(path.read_text());rows={r['tc_id']:r for r in report['cases']}
 if report['phase']!='COMPLETE':raise RuntimeError('Trading execution is still active')
 # The order read schema omits protection fields; absence of a field is not proof of missing behavior.
 r=rows['CT-R007'];r.update(status='BLOCKED',coverage='partial',severity='—',defect_id='—',actual='The pending-order TP edit returned HTTP 200 and retained the existing tickets. The order-read API does not expose a TP field, so the requested protection change could not be verified. No pending-TP product defect is asserted from this observation.',remarks='Partial API check. Requires a supported pending-protection readback or a controlled trigger test. Raw HTTP evidence is retained.')
 browser=json.loads((ROOT/'reports/copy_browser_latest.json').read_text());br={r['tc_id']:r for r in browser['cases']}
 if br['CTUI-007']['status']=='PASS':
  for tid in ['CT-F023','CT-P010']:
   rows[tid].update(status='BLOCKED',coverage='partial',test_data='Chromium; dedicated follower; dashboard reload and Copy Trading widget; no active-trade UI reconciliation.',actual='The logged-in terminal and Copy Trading widget rendered after reload. Offline/online and slow-network loading also succeeded. Live position, subscription and profit/loss reconciliation against backend records was not completed.',remarks='See CTUI-006, CTUI-007, CTUI-010 and CTUI-011. Browser availability is no longer the blocker; active-state reconciliation remains unverified.',script='test_suite/copy_browser_completion_runner.py',reproduce_command='.venv/bin/python test_suite/copy_browser_completion_runner.py --confirm-staging')
 scale_path=ROOT/'reports/copy_scale_latest.json'
 if scale_path.exists():
  scale=json.loads(scale_path.read_text())
  if scale.get('cleanup_verified'):
   sr={r['tc_id']:r for r in scale['cases']}
   for tid,sid in [('CT-R024','CTS-024'),('CT-R027','CTS-027'),('CT-R028','CTS-028')]:
    if sid in sr:
     observation=sr[sid]
     rows[tid].update(status='BLOCKED' if observation['status']=='PASS' else 'FAIL',coverage='partial',test_data=observation['test_data'],actual=observation['actual']+' Database locking, worker distribution and queue internals are not independently verified.',remarks='See '+sid+' in the fresh scale report. This API-level subset does not prove every internal requirement in the specification.',script=observation['script'],reproduce_command=observation['reproduce_command'])
     if observation['status']=='FAIL':rows[tid].update(severity='High',defect_id=observation['defect_id'])
 report['cases']=list(rows.values())
 from collections import Counter
 report['summary']=dict(Counter(r['status'] for r in rows.values()))
 path.write_text(json.dumps(report,indent=2))
 for p in (ROOT/'reports/evidence').glob('master_spec_*/execution.json'):
  if json.loads(p.read_text()).get('started_at')==report['started_at']:
   raw=p.parent/'execution_before_completion_reconciliation.json'
   if not raw.exists():raw.write_text(p.read_text())
   p.write_text(json.dumps(report,indent=2));break
 print('Master-spec result reconciliation:',report['summary'])
if __name__=='__main__':main()
