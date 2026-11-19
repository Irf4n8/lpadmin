# Symbol Coverage - WARN

**Run:** 2026-11-18T15:09:03 (5.7s) | **Instance:** `real` | **Symbols tested:** 18 of 3245 | **Followers:** 1-10 (10 linked)

**Totals:** 9 pass, 0 fail, 8 warn, 1 skipped (market closed)

| Market group | Pass | Fail | Warn | Closed |
| :--- | ---: | ---: | ---: | ---: |
| CFD_247 | 0 | 0 | 1 | 0 |
| CMDTY | 1 | 0 | 0 | 0 |
| CRYPTO/COMMODITY_PERP | 1 | 0 | 0 | 0 |
| CRYPTO/CRYPTO_PERP | 1 | 0 | 0 | 0 |
| CRYPTO/CRYPTO_PERP_COINM | 0 | 0 | 1 | 0 |
| CRYPTO/CRYPTO_SPOT | 1 | 0 | 0 | 0 |
| CRYPTO/STOCK_PERP | 1 | 0 | 0 | 0 |
| CRYPTO_CFD | 0 | 0 | 1 | 0 |
| EU_STOCKS | 1 | 0 | 0 | 0 |
| FOREX | 1 | 0 | 0 | 0 |
| GREEKS | 0 | 0 | 1 | 0 |
| IN_FUTURES | 0 | 0 | 1 | 0 |
| IN_INDEX | 0 | 0 | 1 | 0 |
| IN_OPTIONS | 0 | 0 | 1 | 0 |
| IN_STOCKS | 0 | 0 | 1 | 0 |
| METAL | 1 | 0 | 0 | 0 |
| SPOT_INDICES | 1 | 0 | 0 | 0 |
| US_STOCKS | 0 | 0 | 0 | 1 |

## Problems

- **WARN** `BINANCE:BTCUSD_PERP.P` (CRYPTO/CRYPTO_PERP_COINM): master order rejected: HTTP 400 {"error":"insufficient free margin: required 12909.78, free 899.90","order":{"order_id":"ord_a7ca3479fd680374ea","market_order_id":"ord_a7ca3479fd680374ea","sym
- **WARN** `BLACK:BTCUSD` (CRYPTO_CFD): master order rejected: HTTP 400 {"error":"insufficient free margin: required 1293.26, free 886.71","order":{"order_id":"ord_e1b847b648828e8763","market_order_id":"ord_e1b847b648828e8763","symb
- **WARN** `BLACK:GOLD.247` (CFD_247): master order rejected: HTTP 400 {"error":"insufficient free margin: required 7573.20, free 789.00","order":{"order_id":"ord_7a0a0d7a3259308303","market_order_id":"ord_7a0a0d7a3259308303","symb
- **WARN** `NSE:NIFTY` (IN_INDEX): master order rejected: HTTP 400 {"error":"insufficient free margin: required 5040.61, free 779.96","order":{"order_id":"ord_75950106693dfe42d4","market_order_id":"ord_75950106693dfe42d4","symb
- **WARN** `BSE:SENSEX 03DEC2026 76300 CE` (IN_OPTIONS): master order rejected: HTTP 400 {"error":"insufficient free margin: required 257054.00, free 779.96","order":{"order_id":"ord_8947504b98b4bd32e6","market_order_id":"ord_8947504b98b4bd32e6","sy
- **WARN** `BSE:SENSEX DEC2026 FUT` (IN_FUTURES): master order rejected: HTTP 400 {"error":"insufficient free margin: required 329999.80, free 789.00","order":{"order_id":"ord_36d62ea31219bb42e3","market_order_id":"ord_36d62ea31219bb42e3","sy
- **WARN** `GX:1!BANKNIFTY@FAIR` (GREEKS): master order rejected: HTTP 400 {"error":"insufficient free margin: required 123814.40, free 39.82","order":{"order_id":"ord_7d471ab667ccd4579b","market_order_id":"ord_7d471ab667ccd4579b","sym
- **WARN** `NSE:RELIANCE` (IN_STOCKS): master order rejected: HTTP 400 {"error":"insufficient free margin: required 546.76, free 39.82","order":{"order_id":"ord_d015788d0830617a03","market_order_id":"ord_d015788d0830617a03","symbol

Closed markets are SKIPPED, not failed: re-run during that market's session (Indian NSE/BSE 03:45-10:00 UTC, US stocks ~14:30-21:00 UTC, EU stocks 07:00-15:30 UTC).
