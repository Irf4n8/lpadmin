# Netting vs Hedging Evidence Report

**Generated:** 2026-11-13T04:49:48.772859+00:00  
**Symbol:** `BINANCE:ETHUSDT.P` | **Lot:** 0.1 | **Master:** `ctmaster@mailinator.com`

## real (HEDGING) - 10 followers
_temporary links + wallets created for this run_

| Scenario | Result | Detail |
| :--- | :---: | :--- |
| H5 TP/SL sync | ✅ PASS | master TP/SL stored; followers match model: 10/10 OK (master long 0.2, short 0.0, 1 pos); follower TP/SL equal master (10/10) |
| P1 pending fan-out + cancel | ✅ PASS | master pending orders placed = 3; pending orders fanned out to followers (10/10); all pending orders cancelled everywhere |

## real-net (NETTING) - 10 followers
_temporary links + wallets created for this run_

| Scenario | Result | Detail |
| :--- | :---: | :--- |
| N5 TP/SL on netted position survives add | ❌ FAIL | followers match model: 8/10 wrong - follower1 x1.0: has long 0.2/short 0.0, expected long 0.3000/short 0.0000 / follower2 x2.0: has long 0.4/short 0.0, expected long 0.6000/short 0.0000 / follower3 x3.0: has long 0.6/short 0.0, expected long 0.9000/short 0.0000 / follower4 x0.5: has long 0.1/short 0.0, expected long 0.1500/short 0.0000; follower TP/SL equal master after add (0/10) follower1 tp None sl None; follower2 tp None sl None; follower3 tp None sl None; follower4 tp None sl None |
| P1 pending fan-out + cancel | ❌ FAIL | pending orders fanned out to followers (0/10) follower1, follower2, follower3, follower4, follower5 |

