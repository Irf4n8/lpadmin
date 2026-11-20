export function simplify(records,support){
const actual={
F004:'The follower successfully followed the master and received a copied trade. The subscription screen, risk settings and internal event log were not checked.',
F005:'The follower stopped following the master and received no new copied trades. Other followers continued receiving copies.',
F006:'The master opened a BUY trade. All ten followers received a BUY trade of 0.01 lot.',
F007:'The master opened a SELL trade. All ten followers received a SELL trade of 0.01 lot.',
F008:'The LIMIT order was accepted. The master and all ten followers each had one pending order.',
F009:'The STOP order was accepted. The master and all ten followers each had one pending order.',
F010:'The pending-order price changed on all followers. The existing order tickets were retained; no replacement tickets were created.',
F011:'Cancelling the master’s pending order removed the pending copies from all ten followers.',
F012:'Closing the master’s trade closed all ten follower copies. No position remained on any of the eleven accounts.',
F013:'The master’s trade reduced from 0.04 to 0.02 lot. The 0.5x follower reduced from 0.02 to 0.01 lot. Closing the master’s remainder cleared all accounts.',
F014:'The follower protection orders showed the updated stop-loss of 49,199.92 and take-profit of 73,799.88.',
F015:'The follower protection orders showed take-profit updated to 77,489.87 while stop-loss stayed at 49,199.92.',
F017:'The EURUSD, GBPUSD and USDJPY trades each copied to all ten followers.',
F018:'The master and funded followers opened their trades. The follower with insufficient funds received no position and used no margin.',
F019:'The master’s order was rejected for insufficient margin. No follower position changed.',
F025:'The follower closed its copied trade manually. The later master close left no remaining exposure. This observation alone does not verify every isolation requirement.',
F030:'The closed-trade history matched the position and master reference and included opening/closing times and gross profit or loss. Browser history display was not checked.',
C002:'A 0.04-lot master trade produced a 0.02-lot follower trade at multiplier 0.5.',
C003:'With master equity of 100,000,000 and follower equity of 25,000,000, the follower received the expected 0.01 lot.',
C004:'With master balance of 100,000,000 and follower balance of 50,000,000, the follower received the expected 0.02 lot.',
C007:'The system accepted multiplier 0 and silently saved it as 1x. It should have rejected the invalid value.',
C008:'The system rejected the negative multiplier and returned a validation error stating that the multiplier cannot be below 0.01.',
C014:'The existing follower trade stayed at 0.02 lot. The next trade used the new 2x multiplier, bringing total follower quantity to 0.06 lot. The final master close propagated.',
C015:'The default unfollow behavior was observed. The API did not expose a choice of whether to close or keep existing trades, so the selectable policy was not verified.',
C016:'The underfunded follower received no trade and used no margin. The master and healthy followers traded successfully.',
R001:'Both simultaneous BUY requests succeeded and their copies were verified. The requests completed in 0.125 seconds.',
R002:'The simultaneous BUY and SELL requests both succeeded and their copies were verified. The requests completed in 0.117 seconds.',
R003:'All ten requests succeeded within 0.258 seconds and their follower copies were verified.',
R004:'Immediately cancelling the pending LIMIT order left no pending follower copy.',
R005:'The open-and-close sequence completed in 0.178 seconds. All accounts ended with no open positions.',
R008:'After two quick stop-loss changes, all followers showed the second stop-loss value.',
R011:'Three EURUSD orders placed one second apart each copied once to every follower, with distinct master references.',
R018:'One copied position remained immediately after unfollowing. It closed when the master later closed the trade.',
R019:'Both follow requests returned success, but only one active follower link was created.',
R020:'One unfollow request succeeded and the other returned “not found”. No active follower link remained.',
R021:'Changing settings between trades was tested. The test could not pause an order while copying, so settings applied during an in-flight copy remain unverified.',
R025:'The underfunded follower received no position, while the master and funded followers traded successfully.',
R032:'The master and follower closed at the same time. All accounts ended flat and no server error occurred.',
R049:'The multiplier was changed between trades. Its exact behavior while a copy was still processing could not be observed.',
R051:'After the master closed a BUY and immediately opened a SELL, each of the ten followers held a SELL quantity of 0.01 lot.',
R053:'Closing the master’s copied trade left the follower’s separate manual trade open.',
R054:'The manual order and copied-order request both returned success. The follower ended with one position, used margin of 61.5189 and equity of 99.995. The exact order-processing sequence was not verified.',
R075:'Stopping copying and closing all trades at the same time both succeeded. No positions or active follower links remained.',
N003:'An invalid master account was rejected with a validation error: the account is not an active Copy Trading master.',
N005:'The calculated follower size was 0.0001 lot, below the 0.001-lot minimum. The system increased it to 0.001 lot and filled it instead of rejecting it.',
N006:'The calculated follower size was 150 lots. The system filled 100 lots instead of rejecting the size above the maximum.',
N008:'The master’s order was rejected for insufficient margin. No follower position changed.',
N009:'After admin confirmed the follower was disabled, that follower still received a filled copied order, 15.402 ms after the master. The disabled status was kept for two seconds before restoration.',
N010:'The system rejected the master’s attempt to follow itself, stating that master accounts cannot follow another master.',
N011:'The master’s attempt to follow an existing follower was rejected. A full circular link between two master accounts was not created or tested.',
N012:'All three unauthenticated API requests were rejected with HTTP 401 (authentication required).',
N014:'A text value entered as the multiplier was rejected. Previously saved settings stayed unchanged.',
P001:'Profit/loss calculations matched each account’s own prices. Both accounts had identical entry and exit prices, so different-price slippage was not tested.',
P002:'Gross loss matched the traded quantity: approximately 0.04 on the 0.04-lot master trade and 0.02 on the 0.02-lot follower trade.',
P003:'Closing 0.016 lot recorded the realized profit/loss correctly, left 0.024 lot open and released 40% of used margin.',
P009:'The rejected follower trade created no position. Its balance stayed at 1.',
};
const a={
'002':'The A-book account accepted the BUY order and showed one BUY position.',
'003':'The A-book account accepted the SELL order and showed one SELL position.',
'004':'The A-book master opened a trade. Each of the ten B-book followers received one copied position.',
'005':'The A-book master opened a trade. The A-book follower received one copied position.',
'006':'The B-book master opened a trade. The A-book follower and all B-book control followers each received one copied position.',
'007':'The A-book account accepted the protection update and showed both prices: stop-loss 1.04293 and take-profit 1.15271.',
'008':'The partial close succeeded and left 0.01 lot open.',
'009':'Closing the master’s position left all A-book and B-book test accounts with no open positions.',
'010':'Of eight simultaneous close requests, one succeeded and seven were rejected. The position closed once; no position or used margin remained.',
'011':'Both simultaneous orders succeeded. One BUY and one SELL position of 0.01 lot remained separately open in hedging mode.',
'012':'All six simultaneous BUY requests succeeded, creating six distinct order IDs and six positions.',
'013':'The LIMIT order was accepted and appeared as one pending ticket at price 0.76847.',
'014':'The pending price changed to 0.73005 and the original ticket was retained.',
'015':'Of six simultaneous cancellation requests, one succeeded and five were rejected. No pending order remained.',
};
for(const r of records){
 const old=support.find(s=>s[0]===r[0]);
 if(r[0].startsWith('BTCT-HB-')&&actual[r[0].slice(8)]&&!(r[0]==='BTCT-HB-C015'&&r[7]==='FAIL'))r[6]=actual[r[0].slice(8)];
 if(r[0].startsWith('BTCT-HA-')&&a[r[0].slice(8)])r[6]=a[r[0].slice(8)];
 const net=/^BTCT-N[AB]-(N[1-5]|P1|C1|ISOLATION|ROUTING)$/.exec(r[0]);
 if(net){
 const sid=net[1], book=r[0].startsWith('BTCT-NA')?'A-book master and follower 1; B-book follower 2':'B-book master and both followers';
 r[1]=({N1:'Copy a BUY trade to followers in netting mode',N2:'Reduce a BUY position by placing a smaller SELL',N3:'Change a BUY position to SELL with a larger opposite order',N4:'Close the position with an equal opposite order',N5:'Copy stop-loss and take-profit after increasing a position',P1:'Copy pending LIMIT orders to both followers',C1:'Keep follower quantities correct during simultaneous BUY and SELL orders',ISOLATION:'Close one follower trade without closing the master or other follower',ROUTING:'Verify copied trade quantities under the selected account books'})[sid];
 r[2]=`Three dedicated staging accounts are funded and linked for Copy Trading. Follower 1 uses 1x and follower 2 uses 2x. Start with no open test positions. Routing: ${book}.`;
 r[4]=`Symbol: BLACK:EURUSD\nMode: Real Netting\nFollower 1: 1x; follower 2: 2x\nRouting: ${book}\nOrder quantities: see numbered steps.`;
 const n={N1:'The master held one BUY position of 0.03 lot. Follower 1 held 0.03 lot and follower 2 held 0.06 lot.',N2:'The SELL reduced the master’s BUY to 0.02 lot without opening a separate SELL. Followers held BUY quantities of 0.02 and 0.04 lot.',N3:'The larger SELL changed the master to one SELL position of 0.02 lot. Followers held SELL quantities of 0.02 and 0.04 lot.',N4:'The equal opposite order closed the master’s position and both follower copies. No open position remained.',N5:'Neither follower had the master’s stop-loss or take-profit orders. Both follower protection lists were empty.',P1:'The master’s pending LIMIT orders did not appear on either follower. Neither follower received the expected pending copies.',ISOLATION:'Follower 1 closed its own position. The master stayed BUY 0.03 lot and follower 2 stayed BUY 0.06 lot.',ROUTING:'The master held one BUY position of 0.03 lot. Both followers matched their multipliers: 0.03 and 0.06 lot.'};
 if(n[sid])r[6]=n[sid];
 if(sid==='C1'&&r[7]==='PASS')r[6]='All ten simultaneous orders were accepted. The master ended with one BUY position of 0.02 lot; both followers matched their 1x and 2x quantities. No server error occurred.';
 }
 if(r[0]==='BTCT-NA-C1-R1')r[6]='Follower 1 held BUY 0.04 lot instead of the expected 0.03 lot. The expected quantity was calculated from the master’s accepted orders. This repeat failed.';
 if(r[0]==='BTCT-NA-C1-R2')r[6]='Follower 1 held BUY 0.03 lot instead of the expected 0.02 lot. The expected quantity was calculated from the master’s accepted orders. This repeat failed.';
 if(r[0]==='BTCT-NA-C1-R3')r[6]='The master’s accepted orders produced BUY 0.04 lot. Both follower quantities matched their multipliers. Two SELL requests were explicitly rejected because the liquidity provider was already closing the position. This repeat passed.';
 if(r[7]==='NOT RUN')r[6]='Not tested. Browser/network execution and recovery evidence have not been collected for this scenario.';
 if(r[7]==='BLOCKED')r[6]='Not fully tested. '+r[6].replace(/^Not executed\.\s*/,'').replace(/fixture/g,'test setup').replace(/OMS/g,'order-management system').replace(/LP/g,'liquidity provider');
 if(r[7]==='PARTIAL'&&!/^Partially tested/.test(r[6]))r[6]='Partially tested. '+r[6];
 r[10]=`${r[7]==='PASS'?'Completed recorded API check.':r[7]==='FAIL'?'Observed failure.':r[7]==='PARTIAL'?'Only part of this requirement was checked.':r[7]==='BLOCKED'?'Required access or test setup is missing.':'Planned test; not executed.'} Script and original evidence: see “Scripts and Evidence”, same TC ID. Original ID: ${old?.[1].split(' / ')[0]||r[0]}.`;
}
const simpleCases={
F006:['1. Confirm all ten followers are actively following the master.\n2. Open a master BUY using the recorded symbol and quantity.\n3. Check the side and quantity on all ten followers.','All ten followers receive the correct BUY trade.'],
F007:['1. Confirm all ten followers are actively following the master.\n2. Open a master SELL using the recorded symbol and quantity.\n3. Check the side and quantity on all ten followers.','All ten followers receive the correct SELL trade.'],
F008:['1. Place a master LIMIT order using the recorded price.\n2. Check pending orders on the master and ten followers.','Each follower receives one matching pending LIMIT order.'],
F009:['1. Place a master STOP order using the recorded price.\n2. Check pending orders on the master and ten followers.','Each follower receives one matching pending STOP order.'],
C007:['1. Submit a follower multiplier of 0.\n2. Read the saved multiplier.','Reject multiplier 0 with a clear validation error; do not silently save 1x.'],
R019:['1. Send two follow requests for the same master and follower at the same time.\n2. Check both responses.\n3. Count active follower links.','Create only one active link. Reject the duplicate request with HTTP 409 (conflict).'],
N005:['1. Configure a multiplier that calculates a 0.0001-lot follower trade.\n2. Use a broker minimum of 0.001 lot.\n3. Place the master trade and read follower quantity.','Reject or skip a copied trade below the minimum; do not increase its size without approval.'],
N006:['1. Place a 50-lot master trade with follower multiplier 3x.\n2. Compare the calculated 150 lots with the 100-lot limit.\n3. Read the actual follower quantity.','Reject or skip a copied trade above the maximum; do not silently change its size.'],
N009:['1. Disable the follower through admin and confirm the saved status.\n2. Place a master order while the follower remains disabled.\n3. Check whether the disabled follower receives a copy.\n4. Restore the follower status.','The disabled follower must not receive a new copied trade.'],
};
// Keep the original requirement steps where the full condition was not exercised.
// For completed historical checks, describe the actual executed fixture instead of an unrelated example symbol.
for(const r of records){
 if(r[0].startsWith('BTCT-HB-')&&['PASS','FAIL'].includes(r[7])){
  r[3]=`1. Prepare the master and follower accounts using the test data below.\n2. Perform the action: ${r[1].replace(/^./,c=>c.toLowerCase())}.\n3. Read the resulting orders, positions, subscription or account records through the API.\n4. Compare the result with the expected behavior and restore test account state.`;
 }
}
for(const r of records){const c=r[0].startsWith('BTCT-HB-')?simpleCases[r[0].slice(8)]:null;if(c){r[3]=c[0];r[5]=c[1];}}
const rank={FAIL:0,PASS:1,PARTIAL:2,BLOCKED:3,'NOT RUN':4};
records.sort((a,b)=>rank[a[7]]-rank[b[7]]);
support.sort((a,b)=>records.findIndex(r=>r[0]===a[0])-records.findIndex(r=>r[0]===b[0]));
}
