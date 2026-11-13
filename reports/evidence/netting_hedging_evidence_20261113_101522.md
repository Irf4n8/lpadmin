# Netting vs Hedging Evidence Report

**Generated:** 2026-11-13T04:45:22.689727+00:00  
**Symbol:** `BINANCE:ETHUSDT.P` | **Lot:** 0.1 | **Master:** `ctmaster@mailinator.com`

## paper (HEDGING) - 10 followers
_paper links exist already; none created_

| Scenario | Result | Detail |
| :--- | :---: | :--- |
| H1 BUY and SELL legs coexist | ✅ PASS | master positions (BUY leg + SELL leg stay separate) = 2; master long = 0.1; master short = 0.1 |
| H2 close one leg | ✅ PASS | master long after closing BUY leg = 0.0; master short kept = 0.1; master positions = 1 |
| H3 partial reduce of one leg | ✅ PASS | master long untouched = 0.1; master short reduced by half = 0.05; followers match model: 10/10 OK (master long 0.1, short 0.05, 2 pos) |
| H4 close all | ✅ PASS | master positions after close all = 0; followers flat: 10/10 OK (master long 0.0, short 0.0, 0 pos) |
| P1 pending fan-out + cancel | ✅ PASS | master pending orders placed = 3; pending orders fanned out to followers (10/10); all pending orders cancelled everywhere |
| C1 concurrent BUY/SELL race | ✅ PASS | orders accepted = 10; no 5xx under concurrent BUY/SELL; master hedging legs = 10 |

## paper-net (NETTING) - 0 followers
_paper-net: platform refuses to create copy links on paper accounts -> master-only netting tests_

| Scenario | Result | Detail |
| :--- | :---: | :--- |
| N1 open netted position | ✅ PASS | master positions = 1; master long = 0.3; followers match model: skipped (no followers on this instance) |
| N2 opposite order reduces (one position) | ✅ PASS | master positions (opposite order must NET, not open a 2nd leg) = 1; master long reduced to 2L = 0.2; master short = 0.0 |
| N3 oversized opposite order flips | ✅ PASS | master positions after flip = 1; master long after flip = 0.0; master short = 5L - 3L = 0.2 |
| N4 exact opposite order closes | ✅ PASS | master positions (exact opposite order closes) = 0; followers flat: skipped (no followers on this instance) |
| N5 TP/SL on netted position survives add | ✅ PASS | master TP/SL survive adding to the netted position; master netted size = 0.3; followers match model: skipped (no followers on this instance) |
| P1 pending fan-out + cancel | ✅ PASS | master pending orders placed = 3; all pending orders cancelled everywhere |
| C1 concurrent BUY/SELL race | ✅ PASS | orders accepted = 10; no 5xx under concurrent BUY/SELL; master holds <=1 position (netting invariant) |

