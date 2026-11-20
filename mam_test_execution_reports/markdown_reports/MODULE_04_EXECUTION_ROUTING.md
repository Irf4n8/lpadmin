# Module 4: Order Execution, Modification & Bulk Routing

Rewritten from live evidence. No release sign-off.

## MAM-E001 — Market Order Block Execution and Real-Time Child Ticket Minting

Status: **PARTIAL**

101-account fan-out verified; LP bridge delivery and original <50ms SLA not certified. Server timestamps reported separately.

Evidence checks: MARKET-BUY, LOAD-FIVE-BURST

## MAM-E002 — Pending Limit Order Block Placement and Propagation

Status: **PARTIAL**

Pending ticket fan-out checked on BLACK:BTCUSD; original EURUSD price/allocation fixture replaced by user instruction.

Evidence checks: PENDING-100-FANOUT-LIMIT

## MAM-E003 — Pending Limit Order Trigger and Simultaneous Fill

Status: **PARTIAL**

Marketable limits fill/copy; natural resting-limit crossing, identical fills and simultaneity are not established by these cases.

Evidence checks: PENDING-TRIGGER-LIMIT-BUY, PENDING-TRIGGER-LIMIT-SELL

## MAM-E004 — Master Modifies Stop-Loss and Take-Profit on Open Block

Status: **PARTIAL**

Brackets and prices verified across 101 accounts; original <200ms SLA not certified.

Evidence checks: LIFE-PROTECTION-RETEST, RACE-INDEPENDENT-SL-TP

## MAM-E005 — Master Cancels Pending Limit Order Prior to Fill

Status: **PARTIAL**

All-account pending ticket cancellation checked; see exact child-ticket evidence.

Evidence checks: PENDING-100-FANOUT-LIMIT

## MAM-E006 — Individual Child Stop-Loss Hit at Broker Level

Status: **PARTIAL**

Natural bracket exits observed if triggered; a deliberately isolated single-child SL hit is a separate fixture.

Evidence checks: LIVE-BRACKET-BUY, LIVE-BRACKET-SELL

## MAM-E007 — Individual Child Take-Profit Hit at Broker Level

Status: **PARTIAL**

Natural bracket exits observed if triggered; a deliberately isolated single-child TP hit is a separate fixture.

Evidence checks: LIVE-BRACKET-BUY, LIVE-BRACKET-SELL

## MAM-E008 — Partial Close of Master Order (50% Volume Reduction)

Status: **PARTIAL**

50% child reduction and quantity conservation per position tested; original conserved block sizing differs.

Evidence checks: LIFE-PARTIAL, SIZE-MULTIPLIERS, RACE-MULTI-REDUCE-1

## MAM-E009 — Trailing Stop Block Execution Across Sub-Accounts

Status: **BLOCKED**

This exact execution/terminal/event-ordering fixture was not available or not executed; related market cases do not prove it.

Evidence checks: None; blocked

## MAM-E010 — Full Market Close-All Command by Master

Status: **PARTIAL**

Concurrent parent closes verified flat; UI Close All workflow and <1500ms SLA not certified.

Evidence checks: LOAD-FIVE-BURST, FINAL-FLAT

## MAM-E011 — Out-of-Order Execution Report Handling

Status: **BLOCKED**

This exact execution/terminal/event-ordering fixture was not available or not executed; related market cases do not prove it.

Evidence checks: None; blocked

## MAM-E012 — Sub-Account Real-Time P&L Stream to Mobile App

Status: **BLOCKED**

This exact execution/terminal/event-ordering fixture was not available or not executed; related market cases do not prove it.

Evidence checks: None; blocked

## MAM-E013 — Pending Stop Order (Buy Stop / Sell Stop) Propagation

Status: **PARTIAL**

STOP entry/copy/cancel paths tested on BLACK:BTCUSD; see pending-ticket case for actual pre-trigger behavior.

Evidence checks: PENDING-100-FANOUT-STOP, PENDING-TRIGGER-STOP-BUY, PENDING-TRIGGER-STOP-SELL

## MAM-E014 — Order Expiration (Good 'Til Cancelled vs Day Order)

Status: **BLOCKED**

This exact execution/terminal/event-ordering fixture was not available or not executed; related market cases do not prove it.

Evidence checks: None; blocked

## MAM-E015 — Broker Requote / Price Off Quotes Handling on Parent Order

Status: **BLOCKED**

This exact execution/terminal/event-ordering fixture was not available or not executed; related market cases do not prove it.

Evidence checks: None; blocked

