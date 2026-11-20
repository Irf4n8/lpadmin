"""Append supplied manual browser/network cases without changing execution verdicts."""
import argparse
from collections import Counter
import hashlib
import html
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',required=True)
    args=parser.parse_args()
    source=Path(args.source).read_text()
    groups={'NET':'Network / Slow internet','BR':'Browser switching / Multi-tab','CP':'Copy trading / Browser and network','AL':'Algo trading / Browser and network'}
    related={
        'NET02':('CT-R002','BUY/SELL API concurrency passed; slow-network UI behavior untested.'),
        'NET05':('CT-R008','Rapid API SL updates passed; browser throttling not exercised.'),
        'NET07':('B1 / staging_close_control.json','Concurrent API close core checked; slow browser clicks and retry behavior untested.'),
        'NET08':('B4 / breakpoint_race evidence','Concurrent API cancellation passed; slow browser state untested.'),
        'BR07':('B1 / staging_close_control.json','Single-position API close storm checked; two-browser sessions untested.'),
        'CP08':('CT-R019 / CT-R020','API subscription/unsubscription response contracts failed; cross-browser sequence not executed.'),
        'CP10':('CT-R032','Master/follower concurrent close API check passed; browser workflow not executed.'),
    }
    starters={'NET03','NET07','BR07','BR08','CP04','AL07'}
    cases=[]
    for line in source.splitlines():
        if not re.match(r'^(NET|BR|CP|AL)\d{2}\t',line):continue
        fields=line.split('\t')
        tid,scenario,target=fields[:3]
        group=re.match(r'[A-Z]+',tid)[0]
        priority=fields[3] if len(fields)>3 else 'Not specified'
        pre='Authorized staging/paper account; capture authoritative orders, positions, history and execution IDs.'
        if group=='NET':pre+=' Browser network throttling/offline/reconnect controls.'
        if group=='BR':pre+=' Chrome and Edge or two windows; separate profiles when testing session isolation.'
        if group=='CP':pre+=' Configured master/follower subscription; backend copy records plus browser/network controls.'
        if group=='AL':pre+=' Test algo, defined browser/cloud execution mode and lifecycle controls.'
        ref,note=related.get(tid,('','No equivalent browser/network execution evidence recorded.'))
        cases.append(dict(tc_id=tid,module=groups[group],description=scenario,preconditions=pre,
                          steps=scenario,test_data='Use documented network profile/session setup; not executed.',
                          expected='Verify that the scenario does not cause: '+target,
                          actual='Not executed; added to the manual race/network test plan at user request.',
                          status='NOT RUN',severity='—',defect_id='—',priority=priority,
                          related_execution=ref,remarks=note,priority_starter=tid in starters))
    assert len(cases)==50 and len({r['tc_id'] for r in cases})==50
    assert Counter(r['tc_id'][:2] if not r['tc_id'].startswith('NET') else 'NET' for r in cases)=={'NET':15,'BR':15,'CP':10,'AL':10}
    payload=dict(title='Additional Race Condition / Network / Browser / Algo Test Cases',
                 added_on='2026-11-20',source_sha256=hashlib.sha256(Path(args.source).read_bytes()).hexdigest(),
                 total_cases=50,summary={'NOT RUN':50},priority_starters=sorted(starters),
                 note='Added to the plan only; prior API checks are related evidence, not proof of throttled or cross-browser execution. Test cases are not confirmed bugs.',
                 cases=cases,manual_guide_source=source)
    (ROOT/'reports/network_browser_race_cases.json').write_text(json.dumps(payload,indent=2,ensure_ascii=False))
    (ROOT/'reports/network_browser_race_source.txt').write_text(source)
    esc=lambda x:html.escape(str(x))
    columns=[('tc_id','TC ID'),('module','Module'),('description','Test Case Description'),('preconditions','Pre-Conditions'),
             ('steps','Test Steps'),('test_data','Test Data'),('expected','Expected Result'),('actual','Actual Result'),
             ('status','Status'),('severity','Severity'),('defect_id','Defect ID'),('priority','Priority'),('remarks','Remarks')]
    rows=''
    for r in cases:
        remarks=r['remarks']+(' Related API evidence: '+r['related_execution'] if r['related_execution'] else '')
        if r['priority_starter']:remarks+=' Listed as a priority starter in the source.'
        cells={**r,'remarks':remarks}
        rows+='<tr>'+''.join('<td>'+esc(cells[k])+'</td>' for k,_ in columns)+'</tr>'
    page='<!doctype html><html lang="en"><meta charset="utf-8"><title>Additional Race and Network Test Cases</title><style>body{font:14px system-ui;margin:24px}td,th{border:1px solid #ccd4df;padding:9px;vertical-align:top;text-align:left}table{border-collapse:collapse;width:100%}th{background:#e8eef7;position:sticky;top:0}pre{white-space:pre-wrap;line-height:1.6}input{padding:10px;width:420px}</style>'
    page+='<h1>Additional Race / Network / Browser / Algo Cases</h1><p>50 planned cases: 15 NET, 15 BR, 10 CP and 10 AL. All 50 are NOT RUN. The original 192-case execution results are unchanged; the combined test catalogue now contains 242 cases.</p>'
    page+='<p><a href="master_spec_execution.html">Main execution report</a> · <a href="network_browser_race_cases.json">Case data</a></p>'
    page+='<p>Priority starters: NET03, NET07, BR07, BR08, CP04, AL07. Unspecified priorities are not invented. Prior API evidence does not certify network throttling, WebSocket recovery, browser/session state or algo lifecycle behavior.</p>'
    page+='<p>Multiple deliberate BUY clicks may legitimately place multiple orders. Confirm unintended duplication of one logical action against the documented controls. Browser throttling does not itself verify backend copy or WebSocket behavior.</p>'
    page+='<input aria-label="Filter cases" placeholder="Filter by ID, module, or text" oninput="for(const r of document.querySelectorAll(\'tbody tr\'))r.hidden=!r.textContent.toLowerCase().includes(this.value.toLowerCase())">'
    page+='<table><thead><tr>'+''.join('<th>'+label+'</th>' for _,label in columns)+'</tr></thead><tbody>'+rows+'</tbody></table>'
    page+='<h2>Complete supplied manual guide</h2><p>Includes network profiles, the full NET03 paper-account checklist (repeat 10–20 times), expected reconciliation results, effective combinations, and evidence requirements.</p><pre>'+esc(source)+'</pre></html>'
    (ROOT/'reports/network_browser_race_cases.html').write_text(page)
    print('Added 50 planned test cases: NET15 / BR15 / CP10 / AL10. All NOT RUN; combined catalogue242.')


if __name__=='__main__':main()
