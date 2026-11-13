# Netting vs Hedging Evidence Report

**Generated:** 2026-11-13T04:47:45.516711+00:00  
**Symbol:** `BINANCE:ETHUSDT.P` | **Lot:** 0.1 | **Master:** `ctmaster@mailinator.com`

## real (HEDGING) - 10 followers
_temporary links + wallets created for this run_

| Scenario | Result | Detail |
| :--- | :---: | :--- |
| H1 BUY and SELL legs coexist | ✅ PASS | master positions (BUY leg + SELL leg stay separate) = 2; master long = 0.1; master short = 0.1 |
| H2 close one leg | ✅ PASS | master long after closing BUY leg = 0.0; master short kept = 0.1; master positions = 1 |
| H3 partial reduce of one leg | ✅ PASS | master long untouched = 0.1; master short reduced by half = 0.05; followers match model: 10/10 OK (master long 0.1, short 0.05, 2 pos) |
| H4 close all | ✅ PASS | master positions after close all = 0; followers flat: 10/10 OK (master long 0.0, short 0.0, 0 pos) |
| P1 pending fan-out + cancel | ✅ PASS | master pending orders placed = 3; pending orders fanned out to followers (10/10); all pending orders cancelled everywhere |
| C1 concurrent BUY/SELL race | ✅ PASS | orders accepted = 10; no 5xx under concurrent BUY/SELL; master hedging legs = 10 |

## real-net (NETTING) - 10 followers
_temporary links + wallets created for this run_

| Scenario | Result | Detail |
| :--- | :---: | :--- |
| N1 open netted position | ✅ PASS | master positions = 1; master long = 0.3; followers match model: 10/10 OK (master long 0.3, short 0.0, 1 pos) |
| N2 opposite order reduces (one position) | ✅ PASS | master positions (opposite order must NET, not open a 2nd leg) = 1; master long reduced to 2L = 0.2; master short = 0.0 |
| N3 oversized opposite order flips | ✅ PASS | master positions after flip = 1; master long after flip = 0.0; master short = 5L - 3L = 0.2 |
| N4 exact opposite order closes | ✅ PASS | master positions (exact opposite order closes) = 0; followers flat: 10/10 OK (master long 0.0, short 0.0, 0 pos) |
| N5 TP/SL on netted position survives add | ❌ FAIL | follower TP/SL equal master after add (0/10) follower1 tp None sl None; follower2 tp None sl None; follower3 tp None sl None; follower4 tp None sl None |
| P1 pending fan-out + cancel | ❌ FAIL | pending orders fanned out to followers (0/10) follower1, follower2, follower3, follower4, follower5 |
| C1 concurrent BUY/SELL race | ✅ PASS | orders accepted = 10; no 5xx under concurrent BUY/SELL; master holds <=1 position (netting invariant) |

