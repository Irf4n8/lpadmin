# Module 7: Deposits, Withdrawals & Mid-Trade Disconnections

Rewritten from live evidence. No release sign-off.

## MAM-D001 — Sub-Account Cash Deposit While Trades Are Open

Status: **PARTIAL**

User-requested admin GUI cash update tested; original investor payment-deposit channel not exercised.

Evidence checks: BAL-OPEN-POSITION, GUI-BALANCE-NEXT-ORDER

## MAM-D002 — Partial Withdrawal with Sufficient Free Margin

Status: **PARTIAL**

Admin cash reduction tested; investor withdrawal workflow not exercised.

Evidence checks: BAL-WITHDRAW-HWM

## MAM-D003 — Withdrawal Request Exceeding Free Margin

Status: **BLOCKED**

Requires investor payment/withdrawal, lockup, reversal, or emergency LPOA workflow. Admin Set balance is not a substitute.

Evidence checks: None; blocked

## MAM-D004 — Withdrawal Request During Severe Margin Stress (<120% Margin Level)

Status: **BLOCKED**

Requires investor payment/withdrawal, lockup, reversal, or emergency LPOA workflow. Admin Set balance is not a substitute.

Evidence checks: None; blocked

## MAM-D005 — Emergency LPOA Revocation Mid-Trade: Market Close Option

Status: **PARTIAL**

Unfollow ordering observed; emergency LPOA market-close option not exposed/verified.

Evidence checks: RACE-UNFOLLOW-OPEN-1

## MAM-D006 — Emergency LPOA Revocation Mid-Trade: Transfer Positions Option

Status: **BLOCKED**

Requires investor payment/withdrawal, lockup, reversal, or emergency LPOA workflow. Admin Set balance is not a substitute.

Evidence checks: None; blocked

## MAM-D007 — Manager Group Resizing Post-Investor Disconnection

Status: **PARTIAL**

Active roster changes tested; conserved block allocation redistribution is a different model.

Evidence checks: MAM-UNFOLLOW-FLAT, MAM-JOIN-MIDTRADE

## MAM-D008 — Pending Withdrawal Queued Until Trade Close

Status: **BLOCKED**

Requires investor payment/withdrawal, lockup, reversal, or emergency LPOA workflow. Admin Set balance is not a substitute.

Evidence checks: None; blocked

## MAM-D009 — Locked Capital Period Early Exit Penalty Enforcement

Status: **BLOCKED**

Requires investor payment/withdrawal, lockup, reversal, or emergency LPOA workflow. Admin Set balance is not a substitute.

Evidence checks: None; blocked

## MAM-D010 — Simultaneous Multi-Account Cash Deposits Before Master Trade

Status: **PARTIAL**

One GUI cash change overlaps entry; five simultaneous cleared payment deposits not executed.

Evidence checks: RACE-GUI-BALANCE-ENTRY-1

## MAM-D011 — Large Institutional Whale Deposit Mid-Trade

Status: **PARTIAL**

Doubling follower cash affects future sizing; institutional deposit channel not exercised.

Evidence checks: GUI-BALANCE-NEXT-ORDER

## MAM-D012 — Chargeback / Reversed Deposit on Active MAM Sub-Account

Status: **BLOCKED**

Requires investor payment/withdrawal, lockup, reversal, or emergency LPOA workflow. Admin Set balance is not a substitute.

Evidence checks: None; blocked

## MAM-D013 — Investor Profit-Only Withdrawal While Holding Open Trade Tickets

Status: **BLOCKED**

Requires investor payment/withdrawal, lockup, reversal, or emergency LPOA workflow. Admin Set balance is not a substitute.

Evidence checks: None; blocked

## MAM-D014 — Investor Full Withdrawal with Automatic Position Liquidation

Status: **BLOCKED**

Requires investor payment/withdrawal, lockup, reversal, or emergency LPOA workflow. Admin Set balance is not a substitute.

Evidence checks: None; blocked

## MAM-D015 — Multiple Simultaneous Sub-Account Withdrawals Under Volatility

Status: **BLOCKED**

Requires investor payment/withdrawal, lockup, reversal, or emergency LPOA workflow. Admin Set balance is not a substitute.

Evidence checks: None; blocked

