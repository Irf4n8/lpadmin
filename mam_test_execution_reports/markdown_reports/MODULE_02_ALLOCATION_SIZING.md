# Module 2: MAM Allocation Methods & Sizing Engine

Rewritten from live evidence. No release sign-off.

## MAM-A001 — Proportional by Balance (PBB): 3 Accounts with Equal Balances

Status: **PARTIAL**

Current MAM uses follower/master balance ratios. Original conserved block allocation across subaccounts is a different sizing model.

Evidence checks: SIZE-BALANCE

## MAM-A002 — Proportional by Balance (PBB): Unequal Weighting (10%, 30%, 60%)

Status: **PARTIAL**

Three balance ratios tested; original conserved 10/30/60 percent block allocation not demonstrated.

Evidence checks: SIZE-BALANCE

## MAM-A003 — Proportional by Equity (PBE): Divergent Cash vs Floating Equity

Status: **PARTIAL**

Equity-ratio sizing tested with flat accounts; divergent floating-equity fixture not yet executed.

Evidence checks: SIZE-EQUITY

## MAM-A004 — Predefined Percentage Allocation: Exact Percentage Distribution

Status: **BLOCKED**

The specified allocation policy/currency/conserved-block fixture is not represented by the tested multiplier/balance/equity copy model.

Evidence checks: None; blocked

## MAM-A005 — Predefined Percentage Allocation: Validation of Sum == 100%

Status: **BLOCKED**

The specified allocation policy/currency/conserved-block fixture is not represented by the tested multiplier/balance/equity copy model.

Evidence checks: None; blocked

## MAM-A006 — Lot Multiplier Allocation Method

Status: **PARTIAL**

BLACK:BTCUSD multiplier tiers and partial close tested across 100 followers; the exact 1.00-lot AUDUSD broker-routing fixture was not executed.

Evidence checks: SIZE-MULTIPLIERS

## MAM-A007 — Fixed Lot Allocation Method

Status: **BLOCKED**

The specified allocation policy/currency/conserved-block fixture is not represented by the tested multiplier/balance/equity copy model.

Evidence checks: None; blocked

## MAM-A008 — Equal Risk / Leverage-Weighted Allocation

Status: **BLOCKED**

The specified allocation policy/currency/conserved-block fixture is not represented by the tested multiplier/balance/equity copy model.

Evidence checks: None; blocked

## MAM-A009 — Quantization to Broker Lot Step (0.01 Lot Step Enforcement)

Status: **PARTIAL**

Observed rounding to valid .01 entry steps; original .34999999 boundary fixture not executed.

Evidence checks: SIZE-LOT-RULE-0.03-0.5, SIZE-LOT-RULE-0.01-1.5, SIZE-LOT-RULE-0.01-2.75

## MAM-A010 — Minimum Lot Size Enforcement (0.01 Floor)

Status: **PARTIAL**

BLACK:BTCUSD multiplier-derived .0025 copy size clamps to .01. The original $100 proportional micro-account fixture is different and was not executed.

Evidence checks: SIZE-LOT-RULE-0.01-0.25

## MAM-A011 — Zero-Sum Lot Conservation Law

Status: **BLOCKED**

The specified allocation policy/currency/conserved-block fixture is not represented by the tested multiplier/balance/equity copy model.

Evidence checks: None; blocked

## MAM-A012 — Multi-Currency Balance Conversion at Live Spot Rates

Status: **BLOCKED**

The specified allocation policy/currency/conserved-block fixture is not represented by the tested multiplier/balance/equity copy model.

Evidence checks: None; blocked

## MAM-A013 — Dynamic Equity Fluctuations During Rapid Order Burst

Status: **PARTIAL**

Cash-change/entry races tested; original floating-equity snapshot stress requires a separate oracle.

Evidence checks: RACE-GUI-BALANCE-ENTRY-1, RACE-GUI-BALANCE-ENTRY-2, RACE-GUI-BALANCE-ENTRY-3

## MAM-A014 — Large Block Order Allocation (100.0 Lots Across 20 Accounts)

Status: **PARTIAL**

500 child positions across 100 followers tested; not the specified single 100-lot block.

Evidence checks: LOAD-FIVE-BURST

## MAM-A015 — Small Scalp Order Sizing (0.10 Lots Across 10 Accounts)

Status: **PARTIAL**

Small-ticket copy sizing tested; original conserved .10 block across ten accounts differs from current copy model.

Evidence checks: SIZE-LOT-RULE-0.01-0.25, MARKET-BUY

