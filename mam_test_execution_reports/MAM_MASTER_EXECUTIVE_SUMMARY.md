# MAM live QA report — 20 November 2026

**Release decision: NOT SIGNED OFF.** Executed checks and original-plan coverage are separate. No claim of 165/165 completion or production readiness is made.

Live checks: **{'PASS': 81}** across 81 unique check IDs (includes repeated race trials). Raw attempts: 96.
Original 165 scenarios: **{'BLOCKED': 103, 'PARTIAL': 62}**. PARTIAL is not PASS. The executed BLACK:BTCUSD cases are separately identified below; related checks do not prove every clause of the old plan.

Scope: dedicated test master mamm@mailinator.com and mamf1–mamf100@mailinator.com; real hedging only; BLACK:BTCUSD. No paper/netting trading was tested.

All 101 balances were set to 1,000,000 through actual Playwright Admin → People → Members → member → Real (Hedging) → Set balance, then verified through API reads. Later cases deliberately varied balances and MAM terms. Final account snapshots describe the actual ending state.

## Findings and report integrity

- No platform defect has been confirmed by the validated live assertions in this report. Passing tests do not establish correctness outside their stated scope.
- The separate offline harness audit still reproduces 10 failed checks. These are tooling defects, not 10 newly observed platform defects.
- Historical reports were archived before rewriting in `reports/live_recheck_20261120/historical_reports_before_rewrite.zip`.
- Initial read-only relationship states changed between snapshots before the exclusive test window. No stable platform defect was established from that observation.
- Original requirements include LP routing, fixed-percentage/conserved-block allocation, 500/1000 distinct followers, database locks, failover, time-based fees, and compliance controls. Those are not certified by a B-book 100-follower API/UI run.

## Verified behavior and limits

- BUY/SELL market copying, simultaneous hedged sides, partial/full close, independent follower trades, SL/TP propagation and natural TP exits were exercised.
- Resting LIMIT/STOP tickets were inspected across all 101 accounts and cancelled; marketable pending orders were triggered. These are distinct from an injected gap/slippage test.
- Multiplier, balance and flat-account equity sizing, entry lot rounding, invalid inputs and cross-account position access were checked.
- Repeated close/close, partial/full-close, multiple-reduction, pending modify/cancel, follow/entry, margin-reservation, independent bracket edit, GUI cash/entry and GUI cash/settlement races were exercised.
- Five concurrent master entries created 500 child positions across 100 followers. This does not establish support for 500 distinct followers.
- Per-account settlement, brokerage, recorded manager-share rows and cash-delta/HWM reconciliation were checked. First-profit exemption and subsequent positive fee coverage are governed by the FEE-HWM-POLICY cases below.
- 323 earlier read-only assertions passed: 23 endpoint/auth/account-set checks plus three per follower. These are separate from the live check count.
- Network capture provides observable HTTP evidence; no backend source, database access, broker fault-injection controls or time-control hooks were available.
- GUI/API races establish observed overlapping requests and allowed outcomes, not exact server simultaneity or exhaustive coverage of every interleaving.

## Confirmed defects in the supplied test tooling

The offline regression run reproduced **25 PASS / 10 FAIL**. No fixes to the original application/test-client implementation were made. Full reproductions and source locations are in `reports/QA_REVIEW_20261120.txt` and `reports/qa_retest_20261120.json`.

| ID | Severity | Reproduced problem |
|---|---|---|
| QA-01 | High | F003 reports PASS after both required API calls return 503. |
| QA-02 | High | Local arithmetic with zero platform calls receives a production-ready label. |
| QA-03 | High | Bulk close reports an empty successful cleanup after inventory read failure. |
| QA-04 | High | Bulk cancellation reports success after order inventory read failure. |
| QA-05 | High | Full-close scenario passes when close and verification requests fail. |
| QA-06 | Medium | Authentication reports success without a usable chart token. |
| QA-07 | High | An ambiguous timed-out order POST is automatically replayed without an idempotency guarantee; duplicate execution risk, not a reproduced live duplicate. |
| QA-08 | Medium | Dashboard command validation accepts infinite lot size. |
| QA-09 | Medium | Reversed follower range raises IndexError instead of validation. |
| QA-10 | Medium | Malformed test-operation parameters raise AttributeError instead of returning 400. |

## Final account state

Recorded 2026-11-20T06:16:22.643454+00:00: 101 accounts, 0 open positions, 0 working orders, observed balance values [1000000]. Final relationship validation is recorded in FINAL-ACCOUNT-STATE.

All final cash resets used the actual Admin Member Set balance GUI. The master fee setting is recorded in the final check; the additional mamf4 relationship removed for isolation remains ended. Historic trades and cash adjustments remain in account history.

## Corrected assertions and reruns

- Initial LIFE-PROTECTION failure was a test-oracle error: child brackets link by market_order_id. Corrected all-account set/remove/price check passed. Raw failure retained.
- Initial SETUP-CLEAN verification was blocked by a transient failed read. Subsequent all-account flat checks passed. The original blocked attempt remains in raw evidence.
- The original fee assertion wrongly expected a manager share on the first profitable benchmark crossing. The user explicitly confirmed that first profit is exempt and only subsequent profit with balance already above the benchmark is shared. Both corrected live cases were rerun, including exact share, split conservation, brokerage and balance reconciliation. Earlier failures and the weaker control remain in raw evidence; no platform fee defect is claimed.
- LIVE-BRACKET-SELL: an earlier attempt could not obtain its live-market fixture within the observation window. A later recorded attempt passed; the blocked attempt is preserved, not deleted.
- Lot-rule assertions were strengthened and rerun: exactly one child with the specified rounded quantity is required, and other accounts are checked. Earlier valid-step-only checks were insufficient to prove copying.

## Executed checks

| ID | Result | Check | Evidence |
|---|---|---|---|
| SETUP-BALANCE | PASS | GUI set/read back 1,000,000 on all 101 real-hedging accounts | `reports/live_recheck_20261120/deep_run/results_054434.json`; `http_054434.jsonl.gz` |
| MARKET-BUY | PASS | BLACK BTCUSD BUY -> 100 followers -> master close | `reports/live_recheck_20261120/deep_run/results_054434.json`; `http_054434.jsonl.gz` |
| MARKET-SELL | PASS | BLACK BTCUSD SELL -> 100 followers -> master close | `reports/live_recheck_20261120/deep_run/results_054434.json`; `http_054434.jsonl.gz` |
| LIFE-PARTIAL | PASS | Master 50% partial close replicates remaining quantity to 100 followers | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| LIFE-HEDGE | PASS | Opposite positions coexist; closing BUY preserves SELL across 101 accounts | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| LIFE-FOLLOWER-CLOSE | PASS | Follower manual close does not close master or other followers | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| SIZE-MULTIPLIERS | PASS | Four multiplier tiers across 100 followers, including partial close | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| SIZE-BALANCE | PASS | balance ratio sizing at 0.5x, 1x and 2x balances | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| SIZE-EQUITY | PASS | equity ratio sizing at 0.5x, 1x and 2x balances | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| PENDING-CANCEL-LIMIT-BUY | PASS | Resting BUY LIMIT remains pending then cancels without exposure | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| PENDING-TRIGGER-LIMIT-BUY | PASS | Marketable BUY LIMIT fills and copies to 100 followers | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| PENDING-CANCEL-LIMIT-SELL | PASS | Resting SELL LIMIT remains pending then cancels without exposure | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| PENDING-TRIGGER-LIMIT-SELL | PASS | Marketable SELL LIMIT fills and copies to 100 followers | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| PENDING-CANCEL-STOP-BUY | PASS | Resting BUY STOP remains pending then cancels without exposure | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| PENDING-TRIGGER-STOP-BUY | PASS | Marketable BUY STOP fills and copies to 100 followers | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| PENDING-CANCEL-STOP-SELL | PASS | Resting SELL STOP remains pending then cancels without exposure | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| PENDING-TRIGGER-STOP-SELL | PASS | Marketable SELL STOP fills and copies to 100 followers | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| RACE-PENDING-MODIFY-CANCEL-1 | PASS | Concurrent resting-order edit/cancel does not resurrect order | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| RACE-PENDING-MODIFY-CANCEL-2 | PASS | Concurrent resting-order edit/cancel does not resurrect order | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| RACE-PENDING-MODIFY-CANCEL-3 | PASS | Concurrent resting-order edit/cancel does not resurrect order | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| VALID-ZERO-QTY | PASS | Reject invalid entry without master or follower exposure | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| VALID-NEGATIVE-QTY | PASS | Reject invalid entry without master or follower exposure | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| VALID-BAD-SIDE | PASS | Reject invalid entry without master or follower exposure | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| VALID-BAD-SYMBOL | PASS | Reject invalid entry without master or follower exposure | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| VALID-UNKNOWN-TYPE | PASS | Reject invalid entry without master or follower exposure | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| VALID-LIMIT-WRONG-ENDPOINT | PASS | Reject invalid entry without master or follower exposure | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| VALID-SUBMIN-LOT | PASS | Reject invalid entry without master or follower exposure | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| AUTH-CROSS-ACCOUNT | PASS | Follower cannot close/reduce/protect master-owned position | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| MAM-SELF-FOLLOW | PASS | MAM role and relationship validation: SELF-FOLLOW | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| MAM-UNKNOWN-MASTER | PASS | MAM role and relationship validation: UNKNOWN-MASTER | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| MAM-FOLLOWER-BECOME-MASTER | PASS | MAM role and relationship validation: FOLLOWER-BECOME-MASTER | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| MAM-FEE-CONFIG | PASS | Change manager fee, read back, restore original fee | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| MAM-UNFOLLOW-FLAT | PASS | Unfollow flat account prevents new copies; other followers continue | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| MAM-JOIN-MIDTRADE | PASS | New follower copies future orders without retroactively copying prior trade | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| MAM-MULTIPLIER-MIDTRADE | PASS | Multiplier change affects future copies, not existing position size | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| RACE-UNFOLLOW-OPEN-1 | PASS | Concurrent master entry and follower unfollow produce no duplicate or malformed copy | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| RACE-UNFOLLOW-OPEN-2 | PASS | Concurrent master entry and follower unfollow produce no duplicate or malformed copy | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| RACE-UNFOLLOW-OPEN-3 | PASS | Concurrent master entry and follower unfollow produce no duplicate or malformed copy | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| RACE-CLOSE-1 | PASS | Five concurrent master closes: one history row, no orphan or reversed position | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| RACE-CLOSE-2 | PASS | Five concurrent master closes: one history row, no orphan or reversed position | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| RACE-CLOSE-3 | PASS | Five concurrent master closes: one history row, no orphan or reversed position | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| RACE-MASTER-CHILD-CLOSE | PASS | Concurrent master and follower close: no double booking or orphan | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| RACE-REDUCE-CLOSE | PASS | Concurrent partial close and full close leave all accounts flat | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| BAL-DEPOSIT-HWM | PASS | GUI balance increase moves MAM benchmark by cash delta | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| BAL-WITHDRAW-HWM | PASS | GUI balance decrease moves MAM benchmark by cash delta | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| BAL-OPEN-POSITION | PASS | GUI balance change preserves active copied position and later master close | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| MARGIN-ISOLATION | PASS | Zero-balance follower rejected without blocking other 99 copies | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| RACE-GUI-BALANCE-CLOSE-1 | PASS | GUI follower balance update overlaps master close | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| RACE-GUI-BALANCE-CLOSE-2 | PASS | GUI follower balance update overlaps master close | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| RACE-GUI-BALANCE-CLOSE-3 | PASS | GUI follower balance update overlaps master close | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| LOAD-FIVE-BURST | PASS | Five concurrent entries -> 500 child positions -> concurrent parent closes | `reports/live_recheck_20261120/deep_run/results_054627.json`; `http_054627.jsonl.gz` |
| FINAL-FLAT | PASS | Final real-hedging cleanup across all 101 accounts | `reports/live_recheck_20261120/deep_run/results_060312.json`; `http_060312.jsonl.gz` |
| LIFE-PROTECTION-RETEST | PASS | Set and remove SL/TP across all 101 accounts using actual linkage field | `reports/live_recheck_20261120/deep_run/results_055545.json`; `http_055545.jsonl.gz` |
| SIZE-LOT-RULE-0.01-0.25 | PASS | Copied new entry respects BLACK BTCUSD lot minimum and step | `reports/live_recheck_20261120/deep_run/results_060733.json`; `http_060733.jsonl.gz` |
| SIZE-LOT-RULE-0.03-0.5 | PASS | Copied new entry respects BLACK BTCUSD lot minimum and step | `reports/live_recheck_20261120/deep_run/results_060733.json`; `http_060733.jsonl.gz` |
| SIZE-LOT-RULE-0.01-1.5 | PASS | Copied new entry respects BLACK BTCUSD lot minimum and step | `reports/live_recheck_20261120/deep_run/results_060733.json`; `http_060733.jsonl.gz` |
| SIZE-LOT-RULE-0.01-2.75 | PASS | Copied new entry respects BLACK BTCUSD lot minimum and step | `reports/live_recheck_20261120/deep_run/results_060733.json`; `http_060733.jsonl.gz` |
| ISOLATE-MANUAL-FOLLOWER | PASS | Master close preserves follower independent opposite-side trade | `reports/live_recheck_20261120/deep_run/results_055545.json`; `http_055545.jsonl.gz` |
| RACE-MARGIN-RESERVATION-1 | PASS | Two master entries compete for one follower margin allocation | `reports/live_recheck_20261120/deep_run/results_055545.json`; `http_055545.jsonl.gz` |
| RACE-MARGIN-RESERVATION-2 | PASS | Two master entries compete for one follower margin allocation | `reports/live_recheck_20261120/deep_run/results_055545.json`; `http_055545.jsonl.gz` |
| RACE-MARGIN-RESERVATION-3 | PASS | Two master entries compete for one follower margin allocation | `reports/live_recheck_20261120/deep_run/results_055545.json`; `http_055545.jsonl.gz` |
| RACE-MULTI-REDUCE-1 | PASS | Five reductions cannot close more than original .04 quantity | `reports/live_recheck_20261120/deep_run/results_055545.json`; `http_055545.jsonl.gz` |
| RACE-MULTI-REDUCE-2 | PASS | Five reductions cannot close more than original .04 quantity | `reports/live_recheck_20261120/deep_run/results_055545.json`; `http_055545.jsonl.gz` |
| RACE-MULTI-REDUCE-3 | PASS | Five reductions cannot close more than original .04 quantity | `reports/live_recheck_20261120/deep_run/results_055545.json`; `http_055545.jsonl.gz` |
| RACE-INDEPENDENT-SL-TP | PASS | Concurrent independent bracket edits preserve both supplied fields | `reports/live_recheck_20261120/deep_run/results_055545.json`; `http_055545.jsonl.gz` |
| ACCOUNTING-101 | PASS | Trade price PnL, brokerage, MAM fee transfers and balances reconcile across fleet | `reports/live_recheck_20261120/deep_run/results_055545.json`; `http_055545.jsonl.gz` |
| RACE-GUI-LEDGER-1 | PASS | GUI balance edit versus master close: cash delta, settlement and HWM reconcile | `reports/live_recheck_20261120/deep_run/results_055545.json`; `http_055545.jsonl.gz` |
| RACE-GUI-LEDGER-2 | PASS | GUI balance edit versus master close: cash delta, settlement and HWM reconcile | `reports/live_recheck_20261120/deep_run/results_055545.json`; `http_055545.jsonl.gz` |
| RACE-GUI-LEDGER-3 | PASS | GUI balance edit versus master close: cash delta, settlement and HWM reconcile | `reports/live_recheck_20261120/deep_run/results_055545.json`; `http_055545.jsonl.gz` |
| LIVE-BRACKET-BUY | PASS | Natural live-market SL/TP exit closes copied positions exactly once | `reports/live_recheck_20261120/deep_run/results_055545.json`; `http_055545.jsonl.gz` |
| LIVE-BRACKET-SELL | PASS | Natural live-market SL/TP exit closes copied positions exactly once | `reports/live_recheck_20261120/deep_run/results_060312.json`; `http_060312.jsonl.gz` |
| PENDING-100-FANOUT-LIMIT | PASS | Pending LIMIT tickets appear on all followers and cancel with master | `reports/live_recheck_20261120/deep_run/results_060312.json`; `http_060312.jsonl.gz` |
| PENDING-100-FANOUT-STOP | PASS | Pending STOP tickets appear on all followers and cancel with master | `reports/live_recheck_20261120/deep_run/results_060312.json`; `http_060312.jsonl.gz` |
| GUI-MASTER-CASH-ISOLATION | PASS | Admin master cash adjustment does not transfer cash or resize follower trades | `reports/live_recheck_20261120/deep_run/results_060312.json`; `http_060312.jsonl.gz` |
| GUI-BALANCE-NEXT-ORDER | PASS | Follower cash update changes future ratio size without resizing or misclosing existing trade | `reports/live_recheck_20261120/deep_run/results_060312.json`; `http_060312.jsonl.gz` |
| RACE-GUI-BALANCE-ENTRY-1 | PASS | GUI follower cash change races master entry under balance allocation | `reports/live_recheck_20261120/deep_run/results_060312.json`; `http_060312.jsonl.gz` |
| RACE-GUI-BALANCE-ENTRY-2 | PASS | GUI follower cash change races master entry under balance allocation | `reports/live_recheck_20261120/deep_run/results_060312.json`; `http_060312.jsonl.gz` |
| RACE-GUI-BALANCE-ENTRY-3 | PASS | GUI follower cash change races master entry under balance allocation | `reports/live_recheck_20261120/deep_run/results_060312.json`; `http_060312.jsonl.gz` |
| FINAL-ACCOUNT-STATE | PASS | GUI reset and readback: 101 balances, flat inventory, no pending orders and 100 active multiplier-one links | `reports/live_recheck_20261120/deep_run/results_061323.json`; `http_061323.jsonl.gz` |
| FEE-HWM-POLICY-FIRST | PASS | Confirmed policy: first profitable benchmark crossing has zero manager share | `reports/live_recheck_20261120/deep_run/results_061323.json`; `http_061323.jsonl.gz` |
| FEE-HWM-POLICY-ABOVE | PASS | Confirmed policy: later profit above benchmark shares 50 percent and reconciles balance | `reports/live_recheck_20261120/deep_run/results_061323.json`; `http_061323.jsonl.gz` |

## Original 165-case traceability

| Original ID | Coverage | Requirement | Executed checks / remaining gap |
|---|---|---|---|
| MAM-F001 | BLOCKED | Create Master MAM Group | None — Existing authorized master verified; creation of a new master group and MT5/FIX binding were not performed. |
| MAM-F002 | PARTIAL | Configure Manager Performance Fee and Allocation Profile | MAM-FEE-CONFIG — Fee update/readback/restore tested; monthly crystallization and allocation-profile workflow not verified. |
| MAM-F003 | BLOCKED | Digital Limited Power of Attorney (LPOA) Contract Signing | None — LPOA contracts, independent group-management/archival controls or required role fixtures are not available in the verified API/UI flow. |
| MAM-F004 | PARTIAL | Link Sub-Account to MAM Master Group | MAM-UNFOLLOW-FLAT, MAM-JOIN-MIDTRADE — API leave/rejoin tested; signed LPOA and Bound_Active rights-transfer workflow not verified. |
| MAM-F005 | PARTIAL | Link Sub-Account Below Minimum Balance Threshold | MARGIN-ISOLATION — Zero-capital trade rejection tested; a configured minimum-balance JOIN threshold was not established. |
| MAM-F006 | PARTIAL | Switch MAM Allocation Method on Active Group | SIZE-BALANCE, SIZE-EQUITY — Balance/equity sizing on current MAM tested; immutable configuration audit trail not inspected. |
| MAM-F007 | PARTIAL | Switch Allocation Method While Positions Are Open | MAM-MULTIPLIER-MIDTRADE, GUI-BALANCE-NEXT-ORDER — Future-vs-existing sizing tested; original group allocation-profile transition differs from these follower settings. |
| MAM-F008 | BLOCKED | Multi-Currency Sub-Account Inclusion (USD, EUR, GBP in One Group) | None — LPOA contracts, independent group-management/archival controls or required role fixtures are not available in the verified API/UI flow. |
| MAM-F009 | BLOCKED | Group Maximum Capacity Cap Gating | None — LPOA contracts, independent group-management/archival controls or required role fixtures are not available in the verified API/UI flow. |
| MAM-F010 | PARTIAL | Sub-Account Voluntary Disconnection (Revoking LPOA) With Zero Trades | MAM-UNFOLLOW-FLAT — Unfollow prevents new copies; LPOA revocation, Independent status and manager notification not verified. |
| MAM-F011 | PARTIAL | Sub-Account Disconnection Request While Positions Are Open | RACE-UNFOLLOW-OPEN-1, RACE-UNFOLLOW-OPEN-2, RACE-UNFOLLOW-OPEN-3 — Open/unfollow ordering observed; no contractual close-or-transfer selection workflow was established. |
| MAM-F012 | BLOCKED | Manager Pause / Resume of Individual Sub-Account Participation | None — LPOA contracts, independent group-management/archival controls or required role fixtures are not available in the verified API/UI flow. |
| MAM-F013 | BLOCKED | Multi-Group Manager Configuration | None — LPOA contracts, independent group-management/archival controls or required role fixtures are not available in the verified API/UI flow. |
| MAM-F014 | PARTIAL | Sub-Account Direct Trading Prevention (LPOA Lockout) | ISOLATE-MANUAL-FOLLOWER — Current platform permits independent follower trades. Original LPOA direct-trading lockout requirement is not demonstrated. |
| MAM-F015 | BLOCKED | Manager Voluntary Group Archival / Dissolution | None — LPOA contracts, independent group-management/archival controls or required role fixtures are not available in the verified API/UI flow. |
| MAM-A001 | PARTIAL | Proportional by Balance (PBB): 3 Accounts with Equal Balances | SIZE-BALANCE — Current MAM uses follower/master balance ratios. Original conserved block allocation across subaccounts is a different sizing model. |
| MAM-A002 | PARTIAL | Proportional by Balance (PBB): Unequal Weighting (10%, 30%, 60%) | SIZE-BALANCE — Three balance ratios tested; original conserved 10/30/60 percent block allocation not demonstrated. |
| MAM-A003 | PARTIAL | Proportional by Equity (PBE): Divergent Cash vs Floating Equity | SIZE-EQUITY — Equity-ratio sizing tested with flat accounts; divergent floating-equity fixture not yet executed. |
| MAM-A004 | BLOCKED | Predefined Percentage Allocation: Exact Percentage Distribution | None — The specified allocation policy/currency/conserved-block fixture is not represented by the tested multiplier/balance/equity copy model. |
| MAM-A005 | BLOCKED | Predefined Percentage Allocation: Validation of Sum == 100% | None — The specified allocation policy/currency/conserved-block fixture is not represented by the tested multiplier/balance/equity copy model. |
| MAM-A006 | PARTIAL | Lot Multiplier Allocation Method | SIZE-MULTIPLIERS — BLACK:BTCUSD multiplier tiers and partial close tested across 100 followers; the exact 1.00-lot AUDUSD broker-routing fixture was not executed. |
| MAM-A007 | BLOCKED | Fixed Lot Allocation Method | None — The specified allocation policy/currency/conserved-block fixture is not represented by the tested multiplier/balance/equity copy model. |
| MAM-A008 | BLOCKED | Equal Risk / Leverage-Weighted Allocation | None — The specified allocation policy/currency/conserved-block fixture is not represented by the tested multiplier/balance/equity copy model. |
| MAM-A009 | PARTIAL | Quantization to Broker Lot Step (0.01 Lot Step Enforcement) | SIZE-LOT-RULE-0.03-0.5, SIZE-LOT-RULE-0.01-1.5, SIZE-LOT-RULE-0.01-2.75 — Observed rounding to valid .01 entry steps; original .34999999 boundary fixture not executed. |
| MAM-A010 | PARTIAL | Minimum Lot Size Enforcement (0.01 Floor) | SIZE-LOT-RULE-0.01-0.25 — BLACK:BTCUSD multiplier-derived .0025 copy size clamps to .01. The original $100 proportional micro-account fixture is different and was not executed. |
| MAM-A011 | BLOCKED | Zero-Sum Lot Conservation Law | None — The specified allocation policy/currency/conserved-block fixture is not represented by the tested multiplier/balance/equity copy model. |
| MAM-A012 | BLOCKED | Multi-Currency Balance Conversion at Live Spot Rates | None — The specified allocation policy/currency/conserved-block fixture is not represented by the tested multiplier/balance/equity copy model. |
| MAM-A013 | PARTIAL | Dynamic Equity Fluctuations During Rapid Order Burst | RACE-GUI-BALANCE-ENTRY-1, RACE-GUI-BALANCE-ENTRY-2, RACE-GUI-BALANCE-ENTRY-3 — Cash-change/entry races tested; original floating-equity snapshot stress requires a separate oracle. |
| MAM-A014 | PARTIAL | Large Block Order Allocation (100.0 Lots Across 20 Accounts) | LOAD-FIVE-BURST — 500 child positions across 100 followers tested; not the specified single 100-lot block. |
| MAM-A015 | PARTIAL | Small Scalp Order Sizing (0.10 Lots Across 10 Accounts) | SIZE-LOT-RULE-0.01-0.25, MARKET-BUY — Small-ticket copy sizing tested; original conserved .10 block across ten accounts differs from current copy model. |
| MAM-R001 | PARTIAL | Fractional Remainder Detection (1.00 Lot Across 3 Equal Accounts) | SIZE-LOT-RULE-0.03-0.5 — Copy-size rounding observed; conserved one-lot division across three accounts and remainder ledger not exercised. |
| MAM-R002 | BLOCKED | Remainder Policy: Assign to Highest Equity Sub-Account | None — No configurable remainder-distribution ledger, rebate ledger, or exact block-allocation policy was available for this requirement. |
| MAM-R003 | BLOCKED | Remainder Policy: Absorb into Manager Personal Account | None — No configurable remainder-distribution ledger, rebate ledger, or exact block-allocation policy was available for this requirement. |
| MAM-R004 | BLOCKED | Remainder Policy: Round-Robin Rotation Across Sub-Accounts | None — No configurable remainder-distribution ledger, rebate ledger, or exact block-allocation policy was available for this requirement. |
| MAM-R005 | BLOCKED | Remainder Policy: Truncate / Discard Sub-Cent Residuals | None — No configurable remainder-distribution ledger, rebate ledger, or exact block-allocation policy was available for this requirement. |
| MAM-R006 | BLOCKED | Extreme Fractional Division: 1.00 Lot Across 7 Sub-Accounts | None — No configurable remainder-distribution ledger, rebate ledger, or exact block-allocation policy was available for this requirement. |
| MAM-R007 | PARTIAL | Zero Remainder Perfect Division | SIZE-MULTIPLIERS — Exact multiplier products verified; block remainder-distribution model not exercised. |
| MAM-R008 | PARTIAL | Sub-Minimum Lot Remainder Suppression | SIZE-LOT-RULE-0.01-0.25 — Actual policy clamps below-minimum copies to .01; original remainder suppression policy is a separate requirement. |
| MAM-R009 | BLOCKED | Audit Trail of Remainder Allocation Assignment | None — No configurable remainder-distribution ledger, rebate ledger, or exact block-allocation policy was available for this requirement. |
| MAM-R010 | BLOCKED | Deterministic Remainder Ordering During Equity Ties | None — No configurable remainder-distribution ledger, rebate ledger, or exact block-allocation policy was available for this requirement. |
| MAM-R011 | BLOCKED | Multi-Asset Remainder Handling (Crypto with 8 Decimals vs FX with 2 Decimals) | None — No configurable remainder-distribution ledger, rebate ledger, or exact block-allocation policy was available for this requirement. |
| MAM-R012 | BLOCKED | Cumulative Remainder Lot Drift Over 1,000 Consecutive Trades | None — No configurable remainder-distribution ledger, rebate ledger, or exact block-allocation policy was available for this requirement. |
| MAM-R013 | BLOCKED | Equal Balance Remainder Tie-Breaker Using Account Timestamp | None — No configurable remainder-distribution ledger, rebate ledger, or exact block-allocation policy was available for this requirement. |
| MAM-R014 | PARTIAL | Remainder Handling on Partial Order Close | LIFE-PARTIAL, SIZE-MULTIPLIERS — Proportional remaining quantities tested; configured block-remainder policy not available for verification. |
| MAM-R015 | BLOCKED | Remainder Lot Impact on Broker Volume Rebates | None — No configurable remainder-distribution ledger, rebate ledger, or exact block-allocation policy was available for this requirement. |
| MAM-E001 | PARTIAL | Market Order Block Execution and Real-Time Child Ticket Minting | MARKET-BUY, LOAD-FIVE-BURST — 101-account fan-out verified; LP bridge delivery and original <50ms SLA not certified. Server timestamps reported separately. |
| MAM-E002 | PARTIAL | Pending Limit Order Block Placement and Propagation | PENDING-100-FANOUT-LIMIT — Pending ticket fan-out checked on BLACK:BTCUSD; original EURUSD price/allocation fixture replaced by user instruction. |
| MAM-E003 | PARTIAL | Pending Limit Order Trigger and Simultaneous Fill | PENDING-TRIGGER-LIMIT-BUY, PENDING-TRIGGER-LIMIT-SELL — Marketable limits fill/copy; natural resting-limit crossing, identical fills and simultaneity are not established by these cases. |
| MAM-E004 | PARTIAL | Master Modifies Stop-Loss and Take-Profit on Open Block | LIFE-PROTECTION-RETEST, RACE-INDEPENDENT-SL-TP — Brackets and prices verified across 101 accounts; original <200ms SLA not certified. |
| MAM-E005 | PARTIAL | Master Cancels Pending Limit Order Prior to Fill | PENDING-100-FANOUT-LIMIT — All-account pending ticket cancellation checked; see exact child-ticket evidence. |
| MAM-E006 | PARTIAL | Individual Child Stop-Loss Hit at Broker Level | LIVE-BRACKET-BUY, LIVE-BRACKET-SELL — Natural bracket exits observed if triggered; a deliberately isolated single-child SL hit is a separate fixture. |
| MAM-E007 | PARTIAL | Individual Child Take-Profit Hit at Broker Level | LIVE-BRACKET-BUY, LIVE-BRACKET-SELL — Natural bracket exits observed if triggered; a deliberately isolated single-child TP hit is a separate fixture. |
| MAM-E008 | PARTIAL | Partial Close of Master Order (50% Volume Reduction) | LIFE-PARTIAL, SIZE-MULTIPLIERS, RACE-MULTI-REDUCE-1 — 50% child reduction and quantity conservation per position tested; original conserved block sizing differs. |
| MAM-E009 | BLOCKED | Trailing Stop Block Execution Across Sub-Accounts | None — This exact execution/terminal/event-ordering fixture was not available or not executed; related market cases do not prove it. |
| MAM-E010 | PARTIAL | Full Market Close-All Command by Master | LOAD-FIVE-BURST, FINAL-FLAT — Concurrent parent closes verified flat; UI Close All workflow and <1500ms SLA not certified. |
| MAM-E011 | BLOCKED | Out-of-Order Execution Report Handling | None — This exact execution/terminal/event-ordering fixture was not available or not executed; related market cases do not prove it. |
| MAM-E012 | BLOCKED | Sub-Account Real-Time P&L Stream to Mobile App | None — This exact execution/terminal/event-ordering fixture was not available or not executed; related market cases do not prove it. |
| MAM-E013 | PARTIAL | Pending Stop Order (Buy Stop / Sell Stop) Propagation | PENDING-100-FANOUT-STOP, PENDING-TRIGGER-STOP-BUY, PENDING-TRIGGER-STOP-SELL — STOP entry/copy/cancel paths tested on BLACK:BTCUSD; see pending-ticket case for actual pre-trigger behavior. |
| MAM-E014 | BLOCKED | Order Expiration (Good 'Til Cancelled vs Day Order) | None — This exact execution/terminal/event-ordering fixture was not available or not executed; related market cases do not prove it. |
| MAM-E015 | BLOCKED | Broker Requote / Price Off Quotes Handling on Parent Order | None — This exact execution/terminal/event-ordering fixture was not available or not executed; related market cases do not prove it. |
| MAM-P001 | BLOCKED | Liquidity Provider Partial Fill (50% Block Filled) | None — Requires LP partial-fill, depth, rejection, or routing fault injection; these dedicated accounts are B-book and no LP simulator was supplied. |
| MAM-P002 | PARTIAL | Single Sub-Account Insufficient Margin Rejection (Partial Group Rejection) | MARGIN-ISOLATION, RACE-MARGIN-RESERVATION-1 — Insufficient-margin follower isolation verified; master notification presentation not verified. |
| MAM-P003 | BLOCKED | Atomic All-or-None (AON) Group Execution Policy | None — Requires LP partial-fill, depth, rejection, or routing fault injection; these dedicated accounts are B-book and no LP simulator was supplied. |
| MAM-P004 | BLOCKED | Volume-Weighted Average Price (VWAP) Aggregation | None — Requires LP partial-fill, depth, rejection, or routing fault injection; these dedicated accounts are B-book and no LP simulator was supplied. |
| MAM-P005 | BLOCKED | Direct Pass-Through Price Execution (Independent Fills) | None — Requires LP partial-fill, depth, rejection, or routing fault injection; these dedicated accounts are B-book and no LP simulator was supplied. |
| MAM-P006 | PARTIAL | Slippage Anomaly Detection on Child Orders | ACCOUNTING-101 — Actual per-account fills and price PnL reconciled; configurable slippage-anomaly detection not verified. |
| MAM-P007 | BLOCKED | Sub-Account Account Frozen / Trading Disabled by Compliance | None — Requires LP partial-fill, depth, rejection, or routing fault injection; these dedicated accounts are B-book and no LP simulator was supplied. |
| MAM-P008 | BLOCKED | Partial Fill with Remainder Lot Slicing | None — Requires LP partial-fill, depth, rejection, or routing fault injection; these dedicated accounts are B-book and no LP simulator was supplied. |
| MAM-P009 | BLOCKED | Multi-Tier Liquidity Depth Exhaustion | None — Requires LP partial-fill, depth, rejection, or routing fault injection; these dedicated accounts are B-book and no LP simulator was supplied. |
| MAM-P010 | BLOCKED | Child Order Timeout and Auto-Reconciliation | None — Requires LP partial-fill, depth, rejection, or routing fault injection; these dedicated accounts are B-book and no LP simulator was supplied. |
| MAM-P011 | BLOCKED | Liquidity Provider Rejection on Single Child Order During Fast Market | None — Requires LP partial-fill, depth, rejection, or routing fault injection; these dedicated accounts are B-book and no LP simulator was supplied. |
| MAM-P012 | BLOCKED | Slippage Tolerance Violation on Child Orders | None — Requires LP partial-fill, depth, rejection, or routing fault injection; these dedicated accounts are B-book and no LP simulator was supplied. |
| MAM-P013 | BLOCKED | Fill Price Averaging Across Multi-Currency Accounts | None — Requires LP partial-fill, depth, rejection, or routing fault injection; these dedicated accounts are B-book and no LP simulator was supplied. |
| MAM-P014 | BLOCKED | Asymmetric Rejection Auto-Retry on Secondary Liquidity Bridge | None — Requires LP partial-fill, depth, rejection, or routing fault injection; these dedicated accounts are B-book and no LP simulator was supplied. |
| MAM-P015 | PARTIAL | Orphan Child Order Auto-Cleanup on Parent Order Cancellation | PENDING-100-FANOUT-LIMIT — Pending cancellation/orphan state tested; injected LP child-submission failure not available. |
| MAM-M001 | PARTIAL | Differing Leverage Tiers in Same MAM Group | ACCOUNTING-101 — Current account terms inspected; differing leverage-tier mutation not executed. |
| MAM-M002 | BLOCKED | Isolated Margin Call Warning on Single Sub-Account | None — Requires configured stop-out/leverage/news/swap/notification fixtures beyond the verified account margin cases. |
| MAM-M003 | BLOCKED | Isolated Stop-Out Forced Liquidation on Single Sub-Account | None — Requires configured stop-out/leverage/news/swap/notification fixtures beyond the verified account margin cases. |
| MAM-M004 | BLOCKED | Master Terminal Awareness of Sub-Account Stop-Out | None — Requires configured stop-out/leverage/news/swap/notification fixtures beyond the verified account margin cases. |
| MAM-M005 | BLOCKED | Multiple Sub-Accounts Approaching Margin Call Simultaneously | None — Requires configured stop-out/leverage/news/swap/notification fixtures beyond the verified account margin cases. |
| MAM-M006 | BLOCKED | Negative Balance Protection (NBP) on Single Sub-Account | None — Requires configured stop-out/leverage/news/swap/notification fixtures beyond the verified account margin cases. |
| MAM-M007 | PARTIAL | Sub-Account Margin Requirement Pre-Trade Check | MARGIN-ISOLATION, RACE-MARGIN-RESERVATION-1, RACE-MARGIN-RESERVATION-2, RACE-MARGIN-RESERVATION-3 — Pre-entry margin enforcement and competing reservations verified; see exact observed terms. |
| MAM-M008 | BLOCKED | Free Margin Recalibration Post-Child Stop-Out | None — Requires configured stop-out/leverage/news/swap/notification fixtures beyond the verified account margin cases. |
| MAM-M009 | BLOCKED | Overnight Swap Impact on Independent Margin Levels | None — Requires configured stop-out/leverage/news/swap/notification fixtures beyond the verified account margin cases. |
| MAM-M010 | BLOCKED | Maximum Leverage Limit on Master Terminal Sizing | None — Requires configured stop-out/leverage/news/swap/notification fixtures beyond the verified account margin cases. |
| MAM-M011 | BLOCKED | Sub-Account Stop-Out Recovery via Fresh Deposit While Group Trades | None — Requires configured stop-out/leverage/news/swap/notification fixtures beyond the verified account margin cases. |
| MAM-M012 | PARTIAL | Hedging Margin Requirement on Sub-Accounts | LIFE-HEDGE — Long/short coexistence verified on real hedging; configured special hedging margin offsets not certified. |
| MAM-M013 | BLOCKED | Sub-Account Margin Call Notification to Money Manager GUI | None — Requires configured stop-out/leverage/news/swap/notification fixtures beyond the verified account margin cases. |
| MAM-M014 | BLOCKED | Dynamic Leverage Reduction on High-Impact Economic News | None — Requires configured stop-out/leverage/news/swap/notification fixtures beyond the verified account margin cases. |
| MAM-M015 | BLOCKED | Sub-Account Currency Conversion Margin Cushion | None — Requires configured stop-out/leverage/news/swap/notification fixtures beyond the verified account margin cases. |
| MAM-D001 | PARTIAL | Sub-Account Cash Deposit While Trades Are Open | BAL-OPEN-POSITION, GUI-BALANCE-NEXT-ORDER — User-requested admin GUI cash update tested; original investor payment-deposit channel not exercised. |
| MAM-D002 | PARTIAL | Partial Withdrawal with Sufficient Free Margin | BAL-WITHDRAW-HWM — Admin cash reduction tested; investor withdrawal workflow not exercised. |
| MAM-D003 | BLOCKED | Withdrawal Request Exceeding Free Margin | None — Requires investor payment/withdrawal, lockup, reversal, or emergency LPOA workflow. Admin Set balance is not a substitute. |
| MAM-D004 | BLOCKED | Withdrawal Request During Severe Margin Stress (<120% Margin Level) | None — Requires investor payment/withdrawal, lockup, reversal, or emergency LPOA workflow. Admin Set balance is not a substitute. |
| MAM-D005 | PARTIAL | Emergency LPOA Revocation Mid-Trade: Market Close Option | RACE-UNFOLLOW-OPEN-1 — Unfollow ordering observed; emergency LPOA market-close option not exposed/verified. |
| MAM-D006 | BLOCKED | Emergency LPOA Revocation Mid-Trade: Transfer Positions Option | None — Requires investor payment/withdrawal, lockup, reversal, or emergency LPOA workflow. Admin Set balance is not a substitute. |
| MAM-D007 | PARTIAL | Manager Group Resizing Post-Investor Disconnection | MAM-UNFOLLOW-FLAT, MAM-JOIN-MIDTRADE — Active roster changes tested; conserved block allocation redistribution is a different model. |
| MAM-D008 | BLOCKED | Pending Withdrawal Queued Until Trade Close | None — Requires investor payment/withdrawal, lockup, reversal, or emergency LPOA workflow. Admin Set balance is not a substitute. |
| MAM-D009 | BLOCKED | Locked Capital Period Early Exit Penalty Enforcement | None — Requires investor payment/withdrawal, lockup, reversal, or emergency LPOA workflow. Admin Set balance is not a substitute. |
| MAM-D010 | PARTIAL | Simultaneous Multi-Account Cash Deposits Before Master Trade | RACE-GUI-BALANCE-ENTRY-1 — One GUI cash change overlaps entry; five simultaneous cleared payment deposits not executed. |
| MAM-D011 | PARTIAL | Large Institutional Whale Deposit Mid-Trade | GUI-BALANCE-NEXT-ORDER — Doubling follower cash affects future sizing; institutional deposit channel not exercised. |
| MAM-D012 | BLOCKED | Chargeback / Reversed Deposit on Active MAM Sub-Account | None — Requires investor payment/withdrawal, lockup, reversal, or emergency LPOA workflow. Admin Set balance is not a substitute. |
| MAM-D013 | BLOCKED | Investor Profit-Only Withdrawal While Holding Open Trade Tickets | None — Requires investor payment/withdrawal, lockup, reversal, or emergency LPOA workflow. Admin Set balance is not a substitute. |
| MAM-D014 | BLOCKED | Investor Full Withdrawal with Automatic Position Liquidation | None — Requires investor payment/withdrawal, lockup, reversal, or emergency LPOA workflow. Admin Set balance is not a substitute. |
| MAM-D015 | BLOCKED | Multiple Simultaneous Sub-Account Withdrawals Under Volatility | None — Requires investor payment/withdrawal, lockup, reversal, or emergency LPOA workflow. Admin Set balance is not a substitute. |
| MAM-H001 | PARTIAL | Independent Sub-Account High-Water Mark Baseline Setup | BAL-DEPOSIT-HWM, BAL-WITHDRAW-HWM — Existing relationship benchmarks read and adjusted; independent initial HWM creation workflow not separately certified. |
| MAM-H002 | PARTIAL | Monthly Performance Fee Deduction from Individual Sub-Account | FEE-HWM-POLICY-FIRST, FEE-HWM-POLICY-ABOVE, ACCOUNTING-101 — User-confirmed first-profit exemption and subsequent per-close share tested. Original monthly crystallization is not verified. |
| MAM-H003 | BLOCKED | Drawdown Period: Zero Performance Fee Charged Below Sub-Account HWM | None — Requires time-controlled fee cycles, HWM recovery history, management fees, tax/rebate/statement configuration not available in this run. |
| MAM-H004 | BLOCKED | Recovery Period: Fee Charged ONLY After Breaching Historical Peak | None — Requires time-controlled fee cycles, HWM recovery history, management fees, tax/rebate/statement configuration not available in this run. |
| MAM-H005 | BLOCKED | Exceeding Prior HWM After Full Recovery | None — Requires time-controlled fee cycles, HWM recovery history, management fees, tax/rebate/statement configuration not available in this run. |
| MAM-H006 | PARTIAL | Independent Fee Outcomes: Acc 1 Profitable vs Acc 2 Underwater | ACCOUNTING-101 — Individual fee rows reconciled; simultaneous deliberately profitable/underwater contrast fixture not executed. |
| MAM-H007 | BLOCKED | Annualized Management Fee (AUM Fee) Daily Accrual | None — Requires time-controlled fee cycles, HWM recovery history, management fees, tax/rebate/statement configuration not available in this run. |
| MAM-H008 | PARTIAL | Deposit Proportional HWM Upward Adjustment | BAL-DEPOSIT-HWM — Dollar-for-dollar benchmark movement for admin credit verified; investor payment channel not exercised. |
| MAM-H009 | PARTIAL | Withdrawal Pro-Rata HWM Downward Adjustment | BAL-WITHDRAW-HWM — Current contract moves benchmark by cash delta; original proportional 50% HWM reduction is a different rule. |
| MAM-H010 | PARTIAL | Manager Fee Transfer to Designated Master Trading Wallet | ACCOUNTING-101, FEE-HWM-POLICY-ABOVE — Fee rows and aggregate manager balance receipts checked; distinct designated-wallet routing not exercised. |
| MAM-H011 | BLOCKED | Broker Platform Fee Retainage Split | None — Requires time-controlled fee cycles, HWM recovery history, management fees, tax/rebate/statement configuration not available in this run. |
| MAM-H012 | BLOCKED | Introducing Broker (IB) Commission Rebate from MAM Fees | None — Requires time-controlled fee cycles, HWM recovery history, management fees, tax/rebate/statement configuration not available in this run. |
| MAM-H013 | PARTIAL | Fee Deduction Concurrency with Open Positions | RACE-GUI-LEDGER-1, RACE-GUI-LEDGER-2, RACE-GUI-LEDGER-3 — Cash update/settlement/HWM races tested; retain fee evidence for whether positive manager share occurred. |
| MAM-H014 | BLOCKED | Sub-Account Monthly Statement Fee Itemization | None — Requires time-controlled fee cycles, HWM recovery history, management fees, tax/rebate/statement configuration not available in this run. |
| MAM-H015 | BLOCKED | Clawback Prevention Across Consecutive Cycles | None — Requires time-controlled fee cycles, HWM recovery history, management fees, tax/rebate/statement configuration not available in this run. |
| MAM-C001 | PARTIAL | High-Throughput Ticket Fan-Out: 1 Master Order to 500 Child Tickets | LOAD-FIVE-BURST — Five orders x 100 followers = 500 child positions; not one order to 500 distinct followers. |
| MAM-C002 | PARTIAL | Concurrent Master Order Placement During Sub-Account Deposit Storm | RACE-GUI-BALANCE-ENTRY-1, RACE-GUI-BALANCE-ENTRY-2, RACE-GUI-BALANCE-ENTRY-3 — GUI cash/entry overlaps tested; full deposit storm and internal snapshot isolation not instrumented. |
| MAM-C003 | PARTIAL | Mass SL/TP Modification Fan-Out Across 500 Child Tickets | LIFE-PROTECTION-RETEST — 101 accounts modified; original 500 distinct child-ticket population and SLA not exercised. |
| MAM-C004 | PARTIAL | Simultaneous Order Close and Investor Disconnection | RACE-UNFOLLOW-OPEN-1, RACE-MASTER-CHILD-CLOSE — Related races tested; exact concurrent close/disconnect with contractual settlement policy still requires explicit verification. |
| MAM-C005 | BLOCKED | Idempotency Key Deduplication on Master Block Order | None — Requires infrastructure hooks, a different account population, distributed nodes, gateway idempotency contract, or long-duration load tooling not supplied. |
| MAM-C006 | PARTIAL | Database Row Locking on Sub-Account Balance Ledger | RACE-GUI-LEDGER-1, RACE-MARGIN-RESERVATION-1 — Observable ledger/margin invariants tested; database row-lock wait timing requires backend instrumentation. |
| MAM-C007 | BLOCKED | High-Frequency Tick Burst (500 ticks/sec) During Multi-Order Fan-Out | None — Requires infrastructure hooks, a different account population, distributed nodes, gateway idempotency contract, or long-duration load tooling not supplied. |
| MAM-C008 | BLOCKED | Dead-Letter Queue (DLQ) Handling for Failed Child Order Submissions | None — Requires infrastructure hooks, a different account population, distributed nodes, gateway idempotency contract, or long-duration load tooling not supplied. |
| MAM-C009 | BLOCKED | WebSocket Broadcast Fan-Out to 500 Connected Mobile Apps | None — Requires infrastructure hooks, a different account population, distributed nodes, gateway idempotency contract, or long-duration load tooling not supplied. |
| MAM-C010 | BLOCKED | Memory Leak Profiling Under 100,000 Simulated Child Ticket Lifecycles | None — Requires infrastructure hooks, a different account population, distributed nodes, gateway idempotency contract, or long-duration load tooling not supplied. |
| MAM-C011 | BLOCKED | 1,000 Sub-Accounts Ticket Fan-Out Stress Test | None — Requires infrastructure hooks, a different account population, distributed nodes, gateway idempotency contract, or long-duration load tooling not supplied. |
| MAM-C012 | BLOCKED | Concurrent Child Order Mass Cancellation Across 1,000 Accounts | None — Requires infrastructure hooks, a different account population, distributed nodes, gateway idempotency contract, or long-duration load tooling not supplied. |
| MAM-C013 | PARTIAL | Database Deadlock Prevention via Deterministic Account ID Sorting | RACE-MULTI-REDUCE-1, RACE-MULTI-REDUCE-2, RACE-MULTI-REDUCE-3 — No over-close in repeated races; database lock ordering cannot be inferred from API outcomes. |
| MAM-C014 | BLOCKED | Network Latency Variance Across Geographically Distributed Broker Nodes | None — Requires infrastructure hooks, a different account population, distributed nodes, gateway idempotency contract, or long-duration load tooling not supplied. |
| MAM-C015 | BLOCKED | Distributed Lock (Redlock) Timeout on Allocation Service | None — Requires infrastructure hooks, a different account population, distributed nodes, gateway idempotency contract, or long-duration load tooling not supplied. |
| MAM-L001 | BLOCKED | US NFA Rule 2-43(b) FIFO Enforcement on Sub-Account Positions | None — Requires compliance policy fixtures, jurisdiction controls, document/audit access and authorized evidence. Trading API success cannot establish compliance. |
| MAM-L002 | BLOCKED | ESMA Retail Leverage Cap Enforcement (1:30 Limit) | None — Requires compliance policy fixtures, jurisdiction controls, document/audit access and authorized evidence. Trading API success cannot establish compliance. |
| MAM-L003 | BLOCKED | Digital LPOA Cryptographic Storage and Audit Retrieval | None — Requires compliance policy fixtures, jurisdiction controls, document/audit access and authorized evidence. Trading API success cannot establish compliance. |
| MAM-L004 | BLOCKED | Expired KYC / AML Auto-Gating of Sub-Account | None — Requires compliance policy fixtures, jurisdiction controls, document/audit access and authorized evidence. Trading API success cannot establish compliance. |
| MAM-L005 | BLOCKED | Sanctioned Territory IP Geoblocking on LPOA Submissions | None — Requires compliance policy fixtures, jurisdiction controls, document/audit access and authorized evidence. Trading API success cannot establish compliance. |
| MAM-L006 | BLOCKED | Retail Investor Suitability Questionnaire Verification | None — Requires compliance policy fixtures, jurisdiction controls, document/audit access and authorized evidence. Trading API success cannot establish compliance. |
| MAM-L007 | BLOCKED | Immutable Transaction Audit Logging for Regulatory Audits | None — Requires compliance policy fixtures, jurisdiction controls, document/audit access and authorized evidence. Trading API success cannot establish compliance. |
| MAM-L008 | BLOCKED | Segregated Sub-Account Custody Verification | None — Requires compliance policy fixtures, jurisdiction controls, document/audit access and authorized evidence. Trading API success cannot establish compliance. |
| MAM-L009 | BLOCKED | Anti-Front-Running Compliance Surveillance | None — Requires compliance policy fixtures, jurisdiction controls, document/audit access and authorized evidence. Trading API success cannot establish compliance. |
| MAM-L010 | BLOCKED | GDPR Right to Be Forgotten with Regulatory Ledger Retention | None — Requires compliance policy fixtures, jurisdiction controls, document/audit access and authorized evidence. Trading API success cannot establish compliance. |
| MAM-L011 | BLOCKED | Professional Client Classification for High Leverage (>1:30) | None — Requires compliance policy fixtures, jurisdiction controls, document/audit access and authorized evidence. Trading API success cannot establish compliance. |
| MAM-L012 | BLOCKED | Limited Power of Attorney (LPOA) Expiration and Auto-Pause | None — Requires compliance policy fixtures, jurisdiction controls, document/audit access and authorized evidence. Trading API success cannot establish compliance. |
| MAM-L013 | BLOCKED | Anti-Money Laundering (AML) Closed-Loop Withdrawal Verification | None — Requires compliance policy fixtures, jurisdiction controls, document/audit access and authorized evidence. Trading API success cannot establish compliance. |
| MAM-L014 | BLOCKED | MiFID II Best Execution Audit Reporting on Child Tickets | None — Requires compliance policy fixtures, jurisdiction controls, document/audit access and authorized evidence. Trading API success cannot establish compliance. |
| MAM-L015 | BLOCKED | Automated Statutory Tax Withholding on Manager Performance Fees | None — Requires compliance policy fixtures, jurisdiction controls, document/audit access and authorized evidence. Trading API success cannot establish compliance. |
| MAM-O001 | BLOCKED | Broker Global Emergency Kill-Switch on MAM Group | None — Requires operator/backoffice infrastructure, deployment/failover controls, immutable logs, or external clearing evidence not supplied. |
| MAM-O002 | PARTIAL | Admin Forced Liquidation of Master MAM Positions | FINAL-FLAT — Authorized account cleanup tested with trader APIs; admin forced-liquidation workflow not exercised. |
| MAM-O003 | BLOCKED | Manual Child Ticket Re-Apportionment Console | None — Requires operator/backoffice infrastructure, deployment/failover controls, immutable logs, or external clearing evidence not supplied. |
| MAM-O004 | BLOCKED | Investor Trade Dispute Tick-by-Tick Reconstruction Tool | None — Requires operator/backoffice infrastructure, deployment/failover controls, immutable logs, or external clearing evidence not supplied. |
| MAM-O005 | BLOCKED | Zero-Downtime Rolling Deployment of MAM Allocation Gateway | None — Requires operator/backoffice infrastructure, deployment/failover controls, immutable logs, or external clearing evidence not supplied. |
| MAM-O006 | PARTIAL | Individual Sub-Account Emergency Unlink by Administrator | MAM-UNFOLLOW-FLAT — Follower API unlink tested; administrator emergency unlink workflow not exercised. |
| MAM-O007 | PARTIAL | Administrative Goodwill Balance Adjustment Workflow | SETUP-BALANCE — Actual Admin > Member > Real Hedging > Set balance verified for 101 accounts; treasury debit/immutable audit not certified. |
| MAM-O008 | BLOCKED | Real-Time SRE Alerting on Ticket Fan-Out Latency Spikes (>250ms) | None — Requires operator/backoffice infrastructure, deployment/failover controls, immutable logs, or external clearing evidence not supplied. |
| MAM-O009 | PARTIAL | Automated Daily EOD Reconciliation: Sub-Accounts vs Clearing LP | ACCOUNTING-101 — Account-level reconciliation performed; external clearing LP/EOD reconciliation not accessible on this B-book run. |
| MAM-O010 | BLOCKED | Disaster Recovery Warm Standby Cluster Failover | None — Requires operator/backoffice infrastructure, deployment/failover controls, immutable logs, or external clearing evidence not supplied. |
| MAM-O011 | PARTIAL | Emergency Sub-Account Position Force-Close Without Disconnecting LPOA | LIFE-FOLLOWER-CLOSE — Individual follower close tested; separate administrator force-close privilege path not exercised. |
| MAM-O012 | PARTIAL | Manager Balance Decoupling from Client Sub-Accounts | GUI-MASTER-CASH-ISOLATION — Master cash change isolation tested; personal-account loss and legal custody separation not certified. |
| MAM-O013 | BLOCKED | Historical Performance Tear-Sheet Generator for Prospective Clients | None — Requires operator/backoffice infrastructure, deployment/failover controls, immutable logs, or external clearing evidence not supplied. |
| MAM-O014 | BLOCKED | Audit Log Cryptographic Hashing (SHA-256 Chaining) | None — Requires operator/backoffice infrastructure, deployment/failover controls, immutable logs, or external clearing evidence not supplied. |
| MAM-O015 | BLOCKED | Automated Daily Reconciliation Dispatched to Broker Risk Committee | None — Requires operator/backoffice infrastructure, deployment/failover controls, immutable logs, or external clearing evidence not supplied. |

## Evidence and reproducibility

- `scripts/qa_mam_live.py` and `scripts/qa_mam_additional.py`: authorized mutating live probes. Do not rerun against production funds.
- `reports/live_recheck_20261120/deep_run/results_*.json`: original timestamped attempts and detailed assertions.
- `reports/live_recheck_20261120/deep_run/http_*.jsonl.gz`: request/response evidence without bearer tokens or passwords; gzip JSON Lines.
- `reports/live_recheck_20261120/deep_run/ui_*.png`: real admin GUI balance updates.
- `reports/live_recheck_20261120/deep_run/observed_fanout_latency.json`: server opened_at differences; not browser delivery or LP latency.
- `reports/live_recheck_20261120/validated_checks.csv` and `mam_165_execution_inventory.csv`: machine-readable results and explicit gaps.
