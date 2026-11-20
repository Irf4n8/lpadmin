# Module 5: Partial Fills, Asymmetric Rejections & Slippage

Rewritten from live evidence. No release sign-off.

## MAM-P001 — Liquidity Provider Partial Fill (50% Block Filled)

Status: **BLOCKED**

Requires LP partial-fill, depth, rejection, or routing fault injection; these dedicated accounts are B-book and no LP simulator was supplied.

Evidence checks: None; blocked

## MAM-P002 — Single Sub-Account Insufficient Margin Rejection (Partial Group Rejection)

Status: **PARTIAL**

Insufficient-margin follower isolation verified; master notification presentation not verified.

Evidence checks: MARGIN-ISOLATION, RACE-MARGIN-RESERVATION-1

## MAM-P003 — Atomic All-or-None (AON) Group Execution Policy

Status: **BLOCKED**

Requires LP partial-fill, depth, rejection, or routing fault injection; these dedicated accounts are B-book and no LP simulator was supplied.

Evidence checks: None; blocked

## MAM-P004 — Volume-Weighted Average Price (VWAP) Aggregation

Status: **BLOCKED**

Requires LP partial-fill, depth, rejection, or routing fault injection; these dedicated accounts are B-book and no LP simulator was supplied.

Evidence checks: None; blocked

## MAM-P005 — Direct Pass-Through Price Execution (Independent Fills)

Status: **BLOCKED**

Requires LP partial-fill, depth, rejection, or routing fault injection; these dedicated accounts are B-book and no LP simulator was supplied.

Evidence checks: None; blocked

## MAM-P006 — Slippage Anomaly Detection on Child Orders

Status: **PARTIAL**

Actual per-account fills and price PnL reconciled; configurable slippage-anomaly detection not verified.

Evidence checks: ACCOUNTING-101

## MAM-P007 — Sub-Account Account Frozen / Trading Disabled by Compliance

Status: **BLOCKED**

Requires LP partial-fill, depth, rejection, or routing fault injection; these dedicated accounts are B-book and no LP simulator was supplied.

Evidence checks: None; blocked

## MAM-P008 — Partial Fill with Remainder Lot Slicing

Status: **BLOCKED**

Requires LP partial-fill, depth, rejection, or routing fault injection; these dedicated accounts are B-book and no LP simulator was supplied.

Evidence checks: None; blocked

## MAM-P009 — Multi-Tier Liquidity Depth Exhaustion

Status: **BLOCKED**

Requires LP partial-fill, depth, rejection, or routing fault injection; these dedicated accounts are B-book and no LP simulator was supplied.

Evidence checks: None; blocked

## MAM-P010 — Child Order Timeout and Auto-Reconciliation

Status: **BLOCKED**

Requires LP partial-fill, depth, rejection, or routing fault injection; these dedicated accounts are B-book and no LP simulator was supplied.

Evidence checks: None; blocked

## MAM-P011 — Liquidity Provider Rejection on Single Child Order During Fast Market

Status: **BLOCKED**

Requires LP partial-fill, depth, rejection, or routing fault injection; these dedicated accounts are B-book and no LP simulator was supplied.

Evidence checks: None; blocked

## MAM-P012 — Slippage Tolerance Violation on Child Orders

Status: **BLOCKED**

Requires LP partial-fill, depth, rejection, or routing fault injection; these dedicated accounts are B-book and no LP simulator was supplied.

Evidence checks: None; blocked

## MAM-P013 — Fill Price Averaging Across Multi-Currency Accounts

Status: **BLOCKED**

Requires LP partial-fill, depth, rejection, or routing fault injection; these dedicated accounts are B-book and no LP simulator was supplied.

Evidence checks: None; blocked

## MAM-P014 — Asymmetric Rejection Auto-Retry on Secondary Liquidity Bridge

Status: **BLOCKED**

Requires LP partial-fill, depth, rejection, or routing fault injection; these dedicated accounts are B-book and no LP simulator was supplied.

Evidence checks: None; blocked

## MAM-P015 — Orphan Child Order Auto-Cleanup on Parent Order Cancellation

Status: **PARTIAL**

Pending cancellation/orphan state tested; injected LP child-submission failure not available.

Evidence checks: PENDING-100-FANOUT-LIMIT

