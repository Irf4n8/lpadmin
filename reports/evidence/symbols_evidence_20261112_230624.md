# Symbol Coverage - FAIL

**Run:** 2026-11-12T23:06:24 (1193.7s) | **Instance:** `paper` | **Symbols tested:** 3643 of 3643 | **Followers:** 1-100 (99 linked)

**Totals:** 815 pass, 5 fail, 0 warn, 2823 skipped (market closed)

| Market group | Pass | Fail | Warn | Closed |
| :--- | ---: | ---: | ---: | ---: |
| CFD_247 | 7 | 0 | 0 | 0 |
| CMDTY | 10 | 0 | 0 | 0 |
| CRYPTO/COMMODITY_PERP | 8 | 0 | 0 | 0 |
| CRYPTO/CRYPTO_PERP | 392 | 0 | 0 | 0 |
| CRYPTO/CRYPTO_PERP_COINM | 20 | 0 | 0 | 0 |
| CRYPTO/CRYPTO_SPOT | 50 | 0 | 0 | 0 |
| CRYPTO/STOCK_PERP | 97 | 0 | 0 | 0 |
| CRYPTO_CFD | 42 | 0 | 0 | 0 |
| EU_STOCKS | 0 | 0 | 0 | 33 |
| FOREX | 38 | 4 | 0 | 0 |
| GREEKS | 0 | 0 | 0 | 100 |
| IN_FUTURES | 0 | 0 | 0 | 198 |
| IN_INDEX | 0 | 0 | 0 | 4 |
| IN_OPTIONS | 0 | 0 | 0 | 2388 |
| IN_STOCKS | 0 | 0 | 0 | 100 |
| METAL | 6 | 0 | 0 | 0 |
| SPOT_INDICES | 15 | 1 | 0 | 0 |
| US_STOCKS | 130 | 0 | 0 | 0 |

## Problems

- **FAIL** `BLACK:CADCHF` (FOREX): ctmaster realized PnL -0.071756 but BUY 0.02 0.58639->0.58636 x contract 100000 = -0.06 | follower1 realized PnL -0.071756 but BUY 0.02 0.58639->0.58636 x contract 100000 = -0.06 | follower26 realized PnL -0.143511 but BUY 0.04 0.58639->0.58636 x contract 100000 = -0.12 | follower51 realized PnL -0.215267 but BUY 0.06 0.58639->0.58636 x contract 100000 = -0.18
- **FAIL** `BLACK:CADJPY` (FOREX): ctmaster realized PnL -0.087607 but BUY 0.02 112.069->112.062 x contract 1000 = -0.14 | follower1 realized PnL -0.087607 but BUY 0.02 112.069->112.062 x contract 1000 = -0.14 | follower26 realized PnL -0.175214 but BUY 0.04 112.069->112.062 x contract 1000 = -0.28 | follower51 realized PnL -0.26282 but BUY 0.06 112.069->112.062 x contract 1000 = -0.42 | follower76 realized PnL -0.043803 but BUY 0.01 112.069->112.062 x contract 1000 = -0.07
- **FAIL** `BLACK:CHFJPY` (FOREX): ctmaster realized PnL -0.137692 but BUY 0.02 191.132->191.121 x contract 1000 = -0.22 | follower1 realized PnL -0.137692 but BUY 0.02 191.132->191.121 x contract 1000 = -0.22 | follower26 realized PnL -0.275384 but BUY 0.04 191.132->191.121 x contract 1000 = -0.44 | follower51 realized PnL -0.413075 but BUY 0.06 191.132->191.121 x contract 1000 = -0.66 | follower76 realized PnL -0.068846 but BUY 0.01 191.132->191.121 x contract 1000 = -0.11
- **FAIL** `BLACK:SGDJPY` (FOREX): ctmaster realized PnL -0.262962 but BUY 0.02 124.094->124.073 x contract 1000 = -0.42 | follower1 realized PnL -0.250438 but BUY 0.02 124.094->124.074 x contract 1000 = -0.4 | follower26 realized PnL -0.500875 but BUY 0.04 124.094->124.074 x contract 1000 = -0.8 | follower51 realized PnL -0.751313 but BUY 0.06 124.094->124.074 x contract 1000 = -1.2 | follower76 realized PnL -0.125219 but BUY 0.01 124.094->124.074 x contract 1000 = -0.2
- **FAIL** `BLACK:US30cash-1` (SPOT_INDICES): 24/99 followers did not copy correctly: follower76 expected 0.5 got 1.0; follower77 expected 0.5 got 1.0; follower78 expected 0.5 got 1.0

Closed markets are SKIPPED, not failed: re-run during that market's session (Indian NSE/BSE 03:45-10:00 UTC, US stocks ~14:30-21:00 UTC, EU stocks 07:00-15:30 UTC).
