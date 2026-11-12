# Symbol Coverage - FAIL

**Run:** 2026-11-12T22:56:38 (100.1s) | **Instance:** `paper` | **Symbols tested:** 6 of 3643 | **Followers:** 1-80 (80 linked)

**Totals:** 3 pass, 2 fail, 1 warn, 0 skipped (market closed)

| Market group | Pass | Fail | Warn | Closed |
| :--- | ---: | ---: | ---: | ---: |
| CMDTY | 1 | 0 | 0 | 0 |
| FOREX | 1 | 2 | 1 | 0 |
| METAL | 1 | 0 | 0 | 0 |

## Problems

- **FAIL** `BLACK:EURGBP` (FOREX): follower26 realized PnL -0.052936 but BUY 0.04 0.83538->0.83537 x contract 100000 (type3) = -0.04 | follower51 realized PnL -0.079403 but BUY 0.06 0.83538->0.83537 x contract 100000 (type3) = -0.06
- **FAIL** `BLACK:GBPJPY` (FOREX): ctmaster realized PnL -0.225373 but BUY 0.02 211.402->211.384 x contract 1000 (type3) = -0.36 | follower1 realized PnL -0.225373 but BUY 0.02 211.402->211.384 x contract 1000 (type3) = -0.36 | follower26 realized PnL -0.450746 but BUY 0.04 211.402->211.384 x contract 1000 (type3) = -0.72 | follower51 realized PnL -0.676119 but BUY 0.06 211.402->211.384 x contract 1000 (type3) = -1.08 | follower76 realized PnL -0.112686 but BUY 0.01 211.402->211.384 x contract 1000 (type3) = -0.18
- **WARN** `BLACK:USDJPY` (FOREX): ctmaster realized PnL -0.037562 but BUY 0.02 159.74->159.737 x contract 1000 (type2) = -0.000376 | follower1 realized PnL -0.037562 but BUY 0.02 159.74->159.737 x contract 1000 (type2) = -0.000376 | follower26 realized PnL -0.075123 but BUY 0.04 159.74->159.737 x contract 1000 (type2) = -0.000751 | follower51 realized PnL -0.112685 but BUY 0.06 159.74->159.737 x contract 1000 (type2) = -0.001127 | follower76 realized PnL -0.018781 but BUY 0.01 159.74->159.737 x contract 1000 (type2) = -0.000188

Closed markets are SKIPPED, not failed: re-run during that market's session (Indian NSE/BSE 03:45-10:00 UTC, US stocks ~14:30-21:00 UTC, EU stocks 07:00-15:30 UTC).
