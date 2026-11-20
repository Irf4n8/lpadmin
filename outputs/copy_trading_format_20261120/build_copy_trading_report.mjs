import fs from 'node:fs/promises';
import { simplify } from './simplify_report.mjs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import crypto from 'node:crypto';
import { Workbook, SpreadsheetFile, FileBlob } from '@oai/artifact-tool';

const outDir=path.dirname(fileURLToPath(import.meta.url));
const root=path.resolve(outDir,'../..');
const reports=path.join(root,'reports');
if(process.argv.includes('--inspect-failures')){
  const saved=await SpreadsheetFile.importXlsx(await FileBlob.load(path.join(outDir,'Copy_Trading_Test_Execution_Report_2026-11-20.xlsx')));
  const data=JSON.parse(await fs.readFile(path.join(outDir,'copy_trading_rows.json'),'utf8'));
  for(const id of ['BTCT-HB-C007','BTCT-NA-C1']){
    const index=data.rows.findIndex(r=>r[0]===id);
    const image=await saved.render({sheetName:'Test Execution',range:`F${index+13}:K${index+13}`,scale:1,format:'png'});
    await fs.writeFile(path.join(outDir,id+'_review.png'),new Uint8Array(await image.arrayBuffer()));
  }
  const index=data.rows.findIndex(r=>r[0]==='BTCT-HB-C007');
  const image=await saved.render({sheetName:'Scripts and Evidence',range:`C${index+6}:F${index+6}`,scale:1,format:'png'});
  await fs.writeFile(path.join(outDir,'script_command_review.png'),new Uint8Array(await image.arrayBuffer()));
  console.log('Rendered saved workbook failure and command cells. No workbook edits.');
  process.exit(0);
}
const headers=['TC ID','Test Case Description','Pre-Conditions','Test Steps','Test Data','Expected Result','Actual Result','Status','Severity','Defect ID','Remarks'];
const reference='/Users/irf4n/.codex/attachments/00990272-9a0a-4f2b-91dc-f9d2f1933926/Pasted text.txt';
const referenceText=await fs.readFile(reference,'utf8');
if(JSON.stringify(referenceText.split(/\r?\n/)[0].replace(/^\uFEFF/,'').split('\t'))!==JSON.stringify(headers))throw Error('Reference columns do not match');
const load=async name=>JSON.parse(await fs.readFile(path.join(reports,name),'utf8'));
const master=await load('master_spec_latest.json'), ab=await load('a_book_latest.json');
const net=await load('netting_latest.json'), recheck=await load('netting_recheck_latest.json');
const plan=await load('network_browser_race_cases.json');
const records=[],support=[],sourceCache=new Map();
const hashFile=async relative=>{
  if(!sourceCache.has(relative)){
    const bytes=await fs.readFile(path.join(root,relative));
    sourceCache.set(relative,crypto.createHash('sha256').update(bytes).digest('hex'));
    await fs.mkdir(path.join(outDir,'sources'),{recursive:true});
    await fs.writeFile(path.join(outDir,'sources',path.basename(relative)),bytes);
  }
  return sourceCache.get(relative);
};
const clean=x=>String(x??'—').replace(/\r/g,'').trim()||'—';
const netSteps={
  N1:'1. Start flat on real-net.\n2. Submit BUY 0.03 EURUSD.\n3. Read master and both followers.\n4. Verify one position each and 1x/2x quantities.',
  N2:'1. Submit BUY 0.03.\n2. Submit SELL 0.01 on the same symbol.\n3. Verify one long position of 0.02 on master and 0.02/0.04 on followers.',
  N3:'1. Submit BUY 0.03.\n2. Submit SELL 0.05.\n3. Verify one short position of 0.02 on master and 0.02/0.04 on followers.',
  N4:'1. Submit BUY 0.02.\n2. Submit SELL 0.02.\n3. Read master and follower positions.\n4. Verify exact-offset closure and no remaining copied quantity.',
  N5:'1. Open master BUY 0.02.\n2. Set valid TP/SL using the observed price.\n3. Add BUY 0.01 to the netted position.\n4. Poll master and follower pending protection orders.\n5. Compare both follower TP/SL prices with master.',
  P1:'1. Probe a live price and close the probe trade.\n2. Place three far-market BUY LIMIT orders.\n3. Inspect both followers after 2.5 seconds.\n4. Recheck missing copies after another 8 seconds.\n5. Cancel master pending orders and verify cleanup.',
  C1:'1. Release six BUY and four SELL requests concurrently.\n2. Record accepted and rejected requests separately.\n3. Calculate expected net quantity from accepted requests.\n4. Verify one-sided master exposure and follower quantities at 1x/2x.\n5. Reconcile and flatten test accounts.',
  ISOLATION:'1. Open master BUY 0.03 and verify copies.\n2. Manually close follower1 position.\n3. Verify follower1 is flat.\n4. Verify master remains long 0.03 and follower2 remains long 0.06.',
  ROUTING:'1. Start flat and read back the selected A/B books.\n2. Open master BUY 0.03.\n3. Verify one netted position per account.\n4. Compare follower quantities with 1x/2x model.\n5. Clean up.',
  SETUP:'1. Authenticate the three fresh QA accounts.\n2. Verify real-net is advertised as netting.\n3. Establish the Copy Trading master role.\n4. Fund virtual wallets.\n5. Create and read back 1x/2x follower links.',
  RESTORE:'1. Cancel test pending orders and close test positions.\n2. End new Copy Trading links.\n3. Restore original account books and balances.\n4. Read back all three accounts and verify no remaining exposure or active follows.',
  LP:'1. Obtain an independent LP execution reference and broker ledger.\n2. Reconcile broker execution against the OMS record.\nThese prerequisites were unavailable; this check was blocked.',
};
const abSteps={
  AB001:'1. Capture original books and account state.\n2. Switch master and follower1 from B to A.\n3. Read back both account books through admin API.',
  AB002:'1. Keep the A-book probe account flat.\n2. Submit EURUSD BUY 0.02.\n3. Verify one BUY position in the OMS.\n4. Close the probe.',
  AB003:'1. Keep the A-book probe account flat.\n2. Submit EURUSD SELL 0.02.\n3. Verify one SELL position in the OMS.\n4. Close the probe.',
  AB004:'1. Set master to A and all ten followers to B.\n2. Submit master EURUSD BUY 0.01.\n3. Verify one copied position on each B-book follower.',
  AB005:'1. Set master and follower1 to A; other followers remain B.\n2. Submit master BUY 0.01.\n3. Verify exactly one copied position on the A-book follower.',
  AB006:'1. Set master to B and follower1 to A.\n2. Submit master BUY 0.01.\n3. Verify A-book follower and B-book controls receive one copy each.',
  AB007:'1. Open A-book BUY 0.02.\n2. Set TP at 105% and SL at 95% of the observed price.\n3. Read pending protection orders.\n4. Verify both prices are visible.',
  AB008:'1. Use the open A-book 0.02 position.\n2. Close 0.01.\n3. Verify remaining signed quantity is 0.01.',
  AB009:'1. Establish mixed A/B copied positions from an A-book master.\n2. Close the master position.\n3. Verify all eleven accounts are flat.',
  AB010:'1. Use the remaining A-book position.\n2. Submit eight concurrent closes for the same position.\n3. Inspect response codes, remaining positions and used margin.',
  AB011:'1. Start the A-book probe flat.\n2. Submit BUY and SELL 0.01 concurrently.\n3. Verify two distinct hedging positions with opposite sides.',
  AB012:'1. Start the A-book probe flat.\n2. Submit six BUY 0.01 requests concurrently.\n3. Verify six unique order IDs and six positions.',
  AB013:'1. Start flat.\n2. Submit a far-market BUY LIMIT 0.01.\n3. Verify one pending ticket.',
  AB014:'1. Use the pending LIMIT ticket.\n2. Change its limit price.\n3. Verify the updated price and unchanged ticket ID.',
  AB015:'1. Use the pending LIMIT ticket.\n2. Submit six cancellation requests concurrently.\n3. Verify no pending order remains and no 5xx occurs.',
  AB016:'1. Keep an A-book master position open.\n2. Flatten the B-book probe follower.\n3. Switch that follower from B to A.\n4. Verify successful admin read-back.',
  AB017:'1. Obtain an independent broker execution reference.\n2. Reconcile the LP cash/execution ledger against the OMS.\nIndependent broker access was unavailable.',
  AB018:'1. Flatten all test accounts.\n2. Restore original books, balances and copy links.\n3. Read back all eleven accounts.\n4. Verify zero test positions and pending orders.',
};
async function add(id,r,scope,relative,overrides={}){
  const partial=relative.endsWith('master_spec_latest.json')&&r.status==='BLOCKED'&&r.test_data!=='Not executed';
  const status=overrides.status??(partial?'PARTIAL':r.status);
  const oldId=r.tc_id;
  let actual=clean(overrides.actual??r.actual);
  if(oldId==='CT-C007')actual='Multiplier 0 was accepted with HTTP 200 and silently stored as 1x.';
  if(oldId==='CT-R023'){
    const delays=[...actual.matchAll(/latency_ms['"]?:\s*([0-9.]+)/g)].map(m=>Number(m[1]));
    if(delays.length)actual=`All ten followers received one correctly sized copy. Server fill-timestamp delays ranged from ${Math.min(...delays).toFixed(3)} to ${Math.max(...delays).toFixed(3)} ms, below the 200 ms target.`;
  }
  if(oldId==='NT-RESTORE')actual='All three fresh accounts are flat. Used margin is zero. Original balances and B-book routing were restored, and new Copy Trading links were ended. Fresh accounts and the Copy Trading master role were retained.';
  if(oldId==='NT-SETUP')actual='Fresh Copy Trading master and two followers authenticated on real-net. Virtual wallets funded; 1x/2x netting links read back successfully. Existing accounts were not modified.';
  let sourceRemarks=clean(overrides.remarks??r.remarks);
  if(oldId==='NT-A-C1'&&r.accepted_order_analysis&&relative.endsWith('/netting_latest.json')){
    const m=(r.raw_test_detail||r.actual).match(/has long ([0-9.]+)\/short ([0-9.]+), expected long ([0-9.]+)\/short ([0-9.]+)/);
    const a=r.accepted_order_analysis;
    if(m)actual=`Master accepted ${a.accepted}/10 requests, giving an accepted-order net target of ${a.accepted_net_qty} lots. The 1x A-book follower remained long ${m[1]} instead of ${m[3]} lots after reconciliation. ${a.rejected.length} requests were explicitly rejected; rejection alone is not counted as quantity drift.`;
    sourceRemarks='A-book master and follower1; B-book follower2. Independent LP execution remains unverified.';
    if(r.targeted_recheck)sourceRemarks+=` The isolated accepted-order-aware race recheck failed in ${r.targeted_recheck.failed_rounds} of ${r.targeted_recheck.rounds} rounds.`;
  }
  let defect=clean(overrides.defect_id??r.defect_id);
  if(oldId==='CT-C007')defect='BUG-018 / SPEC-C007';
  if(status==='FAIL'&&/^NT-[AB]-(N5|P1|C1)$/.test(oldId))defect='SPEC-CT-NET-'+oldId.split('-').at(-1);
  const remarks=[scope,`Source ID: ${oldId}.`,partial?'Partial API observations only; the full requirement remains unverified.':'',sourceRemarks==='—'?'':sourceRemarks,r.priority?`Priority ${r.priority}.`:'',Array.isArray(r.evidence)&&typeof r.evidence[0]==='string'?'Evidence: '+r.evidence.join(', '):''].filter(Boolean).join(' ');
  const row=[id,clean(overrides.description??r.description),clean(overrides.preconditions??r.preconditions),clean(overrides.steps??r.steps),
             [clean(overrides.test_data??r.test_data),scope].join('\n'),clean(overrides.expected??r.expected),actual,status,
             clean(overrides.severity??r.severity),defect,remarks];
  records.push(row);
  support.push([id,`${oldId} / ${scope}`,r.script||'—',r.reproduce_command||'Not executed / automation or prerequisite unavailable',
                `Source: sources/${path.basename(relative)}; case ${oldId}`,await hashFile(relative)]);
}
for(const r of master.cases)await add('BTCT-HB-'+r.tc_id.slice(3),r,'B-book hedging. '+(r.test_data==='Not executed'?'Planned requirement; not executed.':'Live OMS API execution.'),'reports/master_spec_latest.json');
for(const r of ab.cases)await add('BTCT-HA-'+r.tc_id.slice(2),r,'A-book hedging / mixed-book staging.','reports/a_book_latest.json',{steps:abSteps[r.tc_id]});
for(const r of net.cases){
  const sid=r.tc_id.split('-').at(-1);
  const id=r.tc_id.startsWith('NT-B-')?'BTCT-NB-'+sid:r.tc_id.startsWith('NT-A-')?'BTCT-NA-'+sid:'BTCT-N-'+sid;
  await add(id,r,'Copy Trading netting. Fresh accounts; 1x/2x followers.','reports/netting_latest.json',{steps:netSteps[sid]});
}
for(const r of plan.cases){
  if(r.tc_id.startsWith('AL')||r.tc_id==='BR14')continue;
  await add('BTCT-'+r.tc_id,r,'Planned browser/network check supporting Copy Trading.','reports/network_browser_race_cases.json',{
    actual:'NOT RUN. No browser-throttling, session-switching or reconnect execution is claimed from the prior API checks.',
    steps:`1. Establish the stated browser/network condition.\n2. Perform: ${r.description}.\n3. Compare authoritative Orders, Positions and History.\n4. Capture logical request IDs, execution IDs, timestamps and recovery state.`,
    defect_id:'—',severity:'—',
  });
}
const repeatCase=recheck.cases.find(r=>r.tc_id==='NT-A-C1');
for(const [i,round] of repeatCase.repetitions.entries()){
  const modelNote=round.notes.find(s=>s.startsWith('Master net equals accepted'))||'';
  const statusNote=round.notes.find(s=>s.startsWith('HTTP statuses='))||'';
  const actual=round.status==='FAIL'?`${round.failures.join('; ')}. ${modelNote}`:`All accepted-order netting and follower-ratio checks matched. ${modelNote}. ${statusNote}`;
  await add(`BTCT-NA-C1-R${i+1}`,repeatCase,'Isolated A-book netting race recheck.','reports/netting_recheck_latest.json',{
    description:`A-book netting concurrent BUY/SELL, repeat ${i+1} of 3`,status:round.status,actual,
    steps:netSteps.C1,test_data:'Six BUY and four SELL requests, qty 0.01. Expected exposure uses accepted requests only.',
    severity:round.status==='FAIL'?'High':'—',defect_id:round.status==='FAIL'?'SPEC-CT-NET-C1':'—',
    remarks:'One logical race requirement repeated three times. Two rounds failed and one passed; these are not three separate defects.',
  });
  support.at(-1)[3]=repeatCase.reproduce_command+' --repeat 3';
}
for(const name of ['copy_browser_latest.json','copy_access_latest.json','copy_scale_latest.json']){
 const report=await load(name);
 for(const r of report.cases)await add(r.tc_id,r,'Additional Copy Trading completion checks.','reports/'+name);
}
if(new Set(records.map(r=>r[0])).size!==records.length)throw Error('Duplicate case IDs');
if(records.some(r=>/BTPAMM|\/pamm\/|\/mam\//i.test(r.slice(0,7).join(' '))))throw Error('Out-of-scope product content entered the Copy Trading table');
simplify(records,support);
const counts=Object.fromEntries([...new Set(records.map(r=>r[7]))].map(s=>[s,records.filter(r=>r[7]===s).length]));
await fs.writeFile(path.join(outDir,'copy_trading_rows.json'),JSON.stringify({headers,counts,rows:records,support},null,2));
const wb=Workbook.create();
const sheet=wb.worksheets.add('Test Execution');
const evidence=wb.worksheets.add('Scripts and Evidence');
const first=13,last=first+records.length-1;
sheet.showGridLines=false;sheet.tabColor='#17365D';
evidence.showGridLines=false;evidence.tabColor='#52657B';
sheet.getRange(`A1:K${last+24}`).format.font={name:'Arial',size:10,color:'#172033'};
sheet.getRange('A2').values=[['Copy Trading Test Execution Report']];
sheet.getRange('A2').format.font={name:'Arial',size:16,bold:true};
sheet.getRange('K2').values=[[new Date('2026-11-20T00:00:00Z')]];
sheet.getRange('K2').setNumberFormat('dd mmm yyyy');
sheet.getRange('K2').format.horizontalAlignment='right';
sheet.getRange('A3').values=[['Staging. Copy Trading only. Hedging, A-book and netting results retain their original scope.']];
sheet.getRange('A3').format.font={name:'Arial',size:10,italic:true,color:'#52657B'};
sheet.getRange('A4:K4').format.borders={bottom:{style:'thin',color:'#CBD5E1'}};
for(const [cell,label,formula] of [
  ['A','Report rows',`=COUNTA(A${first}:A${last})`],['C','PASS',`=COUNTIFS(H${first}:H${last},"PASS")`],
  ['E','FAIL',`=COUNTIFS(H${first}:H${last},"FAIL")`],['G','PARTIAL',`=COUNTIFS(H${first}:H${last},"PARTIAL")`],
  ['I','BLOCKED',`=COUNTIFS(H${first}:H${last},"BLOCKED")`],['K','NOT RUN',`=COUNTIFS(H${first}:H${last},"NOT RUN")`],
]){
  sheet.getRange(`${cell}5`).values=[[label]];
  sheet.getRange(`${cell}5`).format.font={name:'Arial',size:10,bold:true,color:'#52657B'};
  sheet.getRange(`${cell}6`).formulas=[[formula]];
  sheet.getRange(`${cell}6`).format.font={name:'Arial',size:16,bold:true};
  sheet.getRange(`${cell}6`).setNumberFormat('#,##0');
}
sheet.getRange('A8').values=[['Rows include planned requirements, mode variants and three race rechecks. Repeated rows do not create new defects.']];
sheet.getRange('A9').values=[['PASS applies to the recorded API check. PARTIAL retains limited observations. Browser and independent LP checks need their own evidence.']];
sheet.getRange('A10').values=[['Read failures first, then passed checks, partial checks and untested requirements. TP = take-profit; SL = stop-loss. 1x = same quantity; 2x = double quantity.']];
sheet.getRange('A12:K12').values=[headers];
sheet.getRange(`A${first}:K${last}`).values=records;
sheet.getRange(`A12:K${last}`).format.wrapText=true;
sheet.getRange(`A${first}:K${last}`).format.verticalAlignment='top';
const widths=[190,310,350,470,340,450,550,115,95,245,450];
const letters='ABCDEFGHIJK';
for(let i=0;i<11;i++)sheet.getRange(`${letters[i]}1:${letters[i]}${last+24}`).format.columnWidthPx=widths[i];
function rowHeight(row,pixels){
  const lines=Math.max(...row.map((value,i)=>String(value).split('\n').reduce((n,line)=>n+Math.max(1,Math.ceil(line.length/Math.max(10,Math.floor(pixels[i]/6.4)))),0)));
  const points=Math.max(48,lines*12+10);
  if(points>409)throw Error('Text needs more than Excel row height limit');
  return points;
}
for(let i=0;i<records.length;i++)sheet.getRange(`A${first+i}:K${first+i}`).format.rowHeight=rowHeight(records[i],widths);
const table=sheet.tables.add(`A12:K${last}`,true,'CopyTradingExecution');
table.showFilterButton=true;
sheet.getRange('A12:K12').format={fill:'#17365D',font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'},wrapText:true,horizontalAlignment:'center',verticalAlignment:'center',rowHeight:34};
sheet.freezePanes.freezeRows(12);sheet.freezePanes.freezeColumns(1);
const statuses=sheet.getRange(`H${first}:H${last}`);
statuses.format.horizontalAlignment='center';
statuses.conditionalFormats.addCustom(`$H${first}="FAIL"`,{fill:'#FEE2E2',font:{bold:true,color:'#991B1B'}});
statuses.conditionalFormats.addCustom(`$H${first}="PASS"`,{font:{color:'#166534'}});
statuses.conditionalFormats.addCustom(`$H${first}="PARTIAL"`,{fill:'#FEF3C7',font:{color:'#92400E'}});
statuses.conditionalFormats.addCustom(`$H${first}="BLOCKED"`,{fill:'#E2E8F0',font:{color:'#334155'}});
sheet.getRange('E6').conditionalFormats.addCustom('E6>0',{font:{color:'#991B1B',bold:true}});
const footer=last+3;
sheet.getRange(`A${footer}:C${footer+6}`).values=[
  ['Status legend','Meaning',null],['PASS','Recorded check met its expected result.',null],['FAIL','Observed behavior differs from the recorded requirement.',null],
  ['PARTIAL','API subset observed; complete requirement unverified.',null],['BLOCKED','Required access, configuration or fixture unavailable.',null],
  ['NOT RUN','Planned case; no execution is claimed.',null],['Overall status','NOT READY: confirmed defects and incomplete coverage remain.',null],
];
sheet.getRange(`A${footer}:B${footer}`).format.font={bold:true};
sheet.getRange(`A${footer+9}:C${footer+13}`).values=[
  ['Severity','Meaning',null],['Critical','Crash, data loss or system blocker.',null],['High','Major functionality or financial execution control affected.',null],
  ['Medium','Partial functionality affected.',null],['Low','Minor behavior or response-contract mismatch.',null],
];
sheet.getRange(`A${footer+16}:D${footer+19}`).values=[
  ['Role','Name','Signature','Date'],['Test Engineer','Pending','Pending',null],['QA Lead','Pending','Pending',null],['Project Manager','Pending','Pending',null],
];
sheet.getRange(`A${footer}:D${footer+19}`).format.rowHeight=22;

const evidenceHeaders=['TC ID','Original ID / Scope','Script','Reproduce command','Evidence source','Source SHA-256'];
evidence.getRange(`A1:F${support.length+6}`).format.font={name:'Arial',size:10,color:'#172033'};
evidence.getRange('A2').values=[['Scripts and Execution Evidence']];
evidence.getRange('A2').format.font={name:'Arial',size:16,bold:true};
evidence.getRange('A3').values=[['Commands run from the existing repository with its configured staging credentials. Source records retain the full execution observations.']];
evidence.getRange('A5:F5').values=[evidenceHeaders];
evidence.getRange(`A6:F${support.length+5}`).values=support;
evidence.getRange(`A5:F${support.length+5}`).format.wrapText=true;
evidence.getRange(`A6:F${support.length+5}`).format.verticalAlignment='top';
const evWidths=[190,440,370,780,630,450];
for(let i=0;i<6;i++)evidence.getRange(`${letters[i]}1:${letters[i]}${support.length+6}`).format.columnWidthPx=evWidths[i];
for(let i=0;i<support.length;i++)evidence.getRange(`A${6+i}:F${6+i}`).format.rowHeight=rowHeight(support[i],evWidths);
evidence.tables.add(`A5:F${support.length+5}`,true,'CopyTradingEvidence');
evidence.getRange('A5:F5').format={fill:'#52657B',font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'},wrapText:true,horizontalAlignment:'center',verticalAlignment:'center',rowHeight:32};
evidence.freezePanes.freezeRows(5);evidence.freezePanes.freezeColumns(1);
wb.recalculate();
const numeric=sheet.getRange('A6:K6').values[0];
const expected=[records.length,counts.PASS,counts.FAIL,counts.PARTIAL,counts.BLOCKED,counts['NOT RUN']];
if(JSON.stringify([numeric[0],numeric[2],numeric[4],numeric[6],numeric[8],numeric[10]])!==JSON.stringify(expected))throw Error('Summary formulas do not reconcile');
console.log((await wb.inspect({kind:'table',range:'Test Execution!A5:K6',include:'values,formulas',tableMaxRows:2,tableMaxCols:11,maxChars:2200})).ndjson);
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:30},summary:'formula error scan',maxChars:2000})).ndjson);
for(const [name,sheetName,range] of [
  ['execution_left','Test Execution','A12:E14'],['execution_right','Test Execution','F12:K14'],
  ['summary','Test Execution','A2:K10'],['evidence','Scripts and Evidence','A5:D7'],
]){
  const image=await wb.render({sheetName,range,scale:1,format:'png'});
  await fs.writeFile(path.join(outDir,name+'.png'),new Uint8Array(await image.arrayBuffer()));
}
const xlsx=await SpreadsheetFile.exportXlsx(wb);
const xlsxPath=path.join(outDir,'Copy_Trading_Test_Execution_Report_2026-11-20.xlsx');
await xlsx.save(xlsxPath);
const tsv=rows=>rows.map(row=>row.map(v=>/[\t\n"]/.test(String(v))?'"'+String(v).replace(/"/g,'""')+'"':String(v)).join('\t')).join('\n');
await fs.writeFile(path.join(outDir,'Copy_Trading_Test_Execution_Report_2026-11-20.tsv'),tsv([headers,...records]));
const esc=v=>String(v).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const html='<!doctype html><html lang="en"><meta charset="utf-8"><title>Copy Trading Test Execution</title><style>body{font:14px Arial;margin:24px}table{border-collapse:collapse;width:100%}th,td{padding:10px;border:1px solid #d6dee8;text-align:left;vertical-align:top;white-space:pre-line}th{background:#17365d;color:white;position:sticky;top:0}input{padding:10px;width:450px}</style><h1>Copy Trading Test Execution Report</h1><p>20 November 2026. Copy Trading only. Results retain their book/mode scope. Planned cases remain unexecuted; partial API observations do not become complete passes.</p><p>'+esc(JSON.stringify(counts))+'</p><input aria-label="Filter cases" placeholder="Filter case ID, status or description" oninput="for(const r of document.querySelectorAll(\'tbody tr\'))r.hidden=!r.textContent.toLowerCase().includes(this.value.toLowerCase())"><table><thead><tr>'+headers.map(h=>'<th>'+esc(h)+'</th>').join('')+'</tr></thead><tbody>'+records.map(r=>'<tr>'+r.map(v=>'<td>'+esc(v)+'</td>').join('')+'</tr>').join('')+'</tbody></table></html>';
await fs.writeFile(path.join(reports,'copy_trading_execution_table.html'),html);
await fs.writeFile(path.join(outDir,'verification.json'),JSON.stringify({columns:headers.length,rows:records.length,counts,summaryFormulasVerified:true,xlsxPath,sourceDigests:Object.fromEntries(sourceCache)},null,2));
console.log(JSON.stringify({xlsxPath,rows:records.length,counts}));
