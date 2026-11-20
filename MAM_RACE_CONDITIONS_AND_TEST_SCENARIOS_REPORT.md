# MAM race-condition execution report

Real hedging / BLACK:BTCUSD / dedicated simulated accounts. No production sign-off.

- **PASS RACE-PENDING-MODIFY-CANCEL-1** — Concurrent resting-order edit/cancel does not resurrect order; evidence `reports/live_recheck_20261120/deep_run/results_054627.json`.
- **PASS RACE-PENDING-MODIFY-CANCEL-2** — Concurrent resting-order edit/cancel does not resurrect order; evidence `reports/live_recheck_20261120/deep_run/results_054627.json`.
- **PASS RACE-PENDING-MODIFY-CANCEL-3** — Concurrent resting-order edit/cancel does not resurrect order; evidence `reports/live_recheck_20261120/deep_run/results_054627.json`.
- **PASS RACE-UNFOLLOW-OPEN-1** — Concurrent master entry and follower unfollow produce no duplicate or malformed copy; evidence `reports/live_recheck_20261120/deep_run/results_054627.json`.
- **PASS RACE-UNFOLLOW-OPEN-2** — Concurrent master entry and follower unfollow produce no duplicate or malformed copy; evidence `reports/live_recheck_20261120/deep_run/results_054627.json`.
- **PASS RACE-UNFOLLOW-OPEN-3** — Concurrent master entry and follower unfollow produce no duplicate or malformed copy; evidence `reports/live_recheck_20261120/deep_run/results_054627.json`.
- **PASS RACE-CLOSE-1** — Five concurrent master closes: one history row, no orphan or reversed position; evidence `reports/live_recheck_20261120/deep_run/results_054627.json`.
- **PASS RACE-CLOSE-2** — Five concurrent master closes: one history row, no orphan or reversed position; evidence `reports/live_recheck_20261120/deep_run/results_054627.json`.
- **PASS RACE-CLOSE-3** — Five concurrent master closes: one history row, no orphan or reversed position; evidence `reports/live_recheck_20261120/deep_run/results_054627.json`.
- **PASS RACE-MASTER-CHILD-CLOSE** — Concurrent master and follower close: no double booking or orphan; evidence `reports/live_recheck_20261120/deep_run/results_054627.json`.
- **PASS RACE-REDUCE-CLOSE** — Concurrent partial close and full close leave all accounts flat; evidence `reports/live_recheck_20261120/deep_run/results_054627.json`.
- **PASS RACE-GUI-BALANCE-CLOSE-1** — GUI follower balance update overlaps master close; evidence `reports/live_recheck_20261120/deep_run/results_054627.json`.
- **PASS RACE-GUI-BALANCE-CLOSE-2** — GUI follower balance update overlaps master close; evidence `reports/live_recheck_20261120/deep_run/results_054627.json`.
- **PASS RACE-GUI-BALANCE-CLOSE-3** — GUI follower balance update overlaps master close; evidence `reports/live_recheck_20261120/deep_run/results_054627.json`.
- **PASS LOAD-FIVE-BURST** — Five concurrent entries -> 500 child positions -> concurrent parent closes; evidence `reports/live_recheck_20261120/deep_run/results_054627.json`.
- **PASS RACE-MARGIN-RESERVATION-1** — Two master entries compete for one follower margin allocation; evidence `reports/live_recheck_20261120/deep_run/results_055545.json`.
- **PASS RACE-MARGIN-RESERVATION-2** — Two master entries compete for one follower margin allocation; evidence `reports/live_recheck_20261120/deep_run/results_055545.json`.
- **PASS RACE-MARGIN-RESERVATION-3** — Two master entries compete for one follower margin allocation; evidence `reports/live_recheck_20261120/deep_run/results_055545.json`.
- **PASS RACE-MULTI-REDUCE-1** — Five reductions cannot close more than original .04 quantity; evidence `reports/live_recheck_20261120/deep_run/results_055545.json`.
- **PASS RACE-MULTI-REDUCE-2** — Five reductions cannot close more than original .04 quantity; evidence `reports/live_recheck_20261120/deep_run/results_055545.json`.
- **PASS RACE-MULTI-REDUCE-3** — Five reductions cannot close more than original .04 quantity; evidence `reports/live_recheck_20261120/deep_run/results_055545.json`.
- **PASS RACE-INDEPENDENT-SL-TP** — Concurrent independent bracket edits preserve both supplied fields; evidence `reports/live_recheck_20261120/deep_run/results_055545.json`.
- **PASS RACE-GUI-LEDGER-1** — GUI balance edit versus master close: cash delta, settlement and HWM reconcile; evidence `reports/live_recheck_20261120/deep_run/results_055545.json`.
- **PASS RACE-GUI-LEDGER-2** — GUI balance edit versus master close: cash delta, settlement and HWM reconcile; evidence `reports/live_recheck_20261120/deep_run/results_055545.json`.
- **PASS RACE-GUI-LEDGER-3** — GUI balance edit versus master close: cash delta, settlement and HWM reconcile; evidence `reports/live_recheck_20261120/deep_run/results_055545.json`.
- **PASS RACE-GUI-BALANCE-ENTRY-1** — GUI follower cash change races master entry under balance allocation; evidence `reports/live_recheck_20261120/deep_run/results_060312.json`.
- **PASS RACE-GUI-BALANCE-ENTRY-2** — GUI follower cash change races master entry under balance allocation; evidence `reports/live_recheck_20261120/deep_run/results_060312.json`.
- **PASS RACE-GUI-BALANCE-ENTRY-3** — GUI follower cash change races master entry under balance allocation; evidence `reports/live_recheck_20261120/deep_run/results_060312.json`.

Thread-barrier races and GUI/API overlapping operations were observed; exact server simultaneity and all possible interleavings are not claimed.
