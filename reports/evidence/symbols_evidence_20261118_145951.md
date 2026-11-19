# Symbol Coverage - WARN

**Run:** 2026-11-18T14:59:51 (7.2s) | **Instance:** `real` | **Symbols tested:** 18 of 3245 | **Followers:** 1-10 (10 linked)

**Totals:** 12 pass, 0 fail, 5 warn, 1 skipped (market closed)

| Market group | Pass | Fail | Warn | Closed |
| :--- | ---: | ---: | ---: | ---: |
| CFD_247 | 0 | 0 | 1 | 0 |
| CMDTY | 1 | 0 | 0 | 0 |
| CRYPTO/COMMODITY_PERP | 1 | 0 | 0 | 0 |
| CRYPTO/CRYPTO_PERP | 1 | 0 | 0 | 0 |
| CRYPTO/CRYPTO_PERP_COINM | 0 | 0 | 1 | 0 |
| CRYPTO/CRYPTO_SPOT | 1 | 0 | 0 | 0 |
| CRYPTO/STOCK_PERP | 1 | 0 | 0 | 0 |
| CRYPTO_CFD | 1 | 0 | 0 | 0 |
| EU_STOCKS | 1 | 0 | 0 | 0 |
| FOREX | 1 | 0 | 0 | 0 |
| GREEKS | 0 | 0 | 1 | 0 |
| IN_FUTURES | 0 | 0 | 1 | 0 |
| IN_INDEX | 1 | 0 | 0 | 0 |
| IN_OPTIONS | 0 | 0 | 1 | 0 |
| IN_STOCKS | 1 | 0 | 0 | 0 |
| METAL | 1 | 0 | 0 | 0 |
| SPOT_INDICES | 1 | 0 | 0 | 0 |
| US_STOCKS | 0 | 0 | 0 | 1 |

## Problems

- **WARN** `BINANCE:BTCUSD_PERP.P` (CRYPTO/CRYPTO_PERP_COINM): master order rejected: HTTP 400 {"error":"insufficient free margin: required 12916.54, free 9728.03","order":{"order_id":"ord_391a2b9c5f599d3899","market_order_id":"ord_391a2b9c5f599d3899","sy
- **WARN** `BLACK:GOLD.247` (CFD_247): master order rejected: HTTP 400 {"error":"insufficient free margin: required 7563.00, free 7518.47","order":{"order_id":"ord_794eb4ad6bae2d16dd","market_order_id":"ord_794eb4ad6bae2d16dd","sym
- **WARN** `BSE:SENSEX 03DEC2026 76300 CE` (IN_OPTIONS): master order rejected: HTTP 400 {"error":"feed stale for BSE:SENSEX 03DEC2026 76300 CE (no live tick in 90s)","order":{"order_id":"ord_43ed826cfc3c4728cc","market_order_id":"ord_43ed826cfc3c47
- **WARN** `BSE:SENSEX DEC2026 FUT` (IN_FUTURES): master order rejected: HTTP 400 {"error":"insufficient free margin: required 330000.00, free 2474.89","order":{"order_id":"ord_0d3f6e883edf70a40c","market_order_id":"ord_0d3f6e883edf70a40c","s
- **WARN** `GX:1!BANKNIFTY@FAIR` (GREEKS): master order rejected: HTTP 400 {"error":"insufficient free margin: required 123858.60, free 2474.89","order":{"order_id":"ord_3a1adaf56fbd83c7d8","market_order_id":"ord_3a1adaf56fbd83c7d8","s

Closed markets are SKIPPED, not failed: re-run during that market's session (Indian NSE/BSE 03:45-10:00 UTC, US stocks ~14:30-21:00 UTC, EU stocks 07:00-15:30 UTC).
