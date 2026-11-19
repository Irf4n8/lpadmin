# Symbol Coverage - FAIL

**Run:** 2026-11-18T15:15:31 (35.3s) | **Instance:** `real` | **Symbols tested:** 18 of 3245 | **Followers:** 1-10 (10 linked)

**Totals:** 8 pass, 1 fail, 8 warn, 1 skipped (market closed)

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
| SPOT_INDICES | 0 | 1 | 0 | 0 |
| US_STOCKS | 0 | 0 | 0 | 1 |

## Problems

- **WARN** `BINANCE:BTCUSD_PERP.P` (CRYPTO/CRYPTO_PERP_COINM): master order rejected: HTTP 400 {"error":"insufficient free margin: required 12905.58, free 887.94","order":{"order_id":"ord_b562a29b48e6f638e9","market_order_id":"ord_b562a29b48e6f638e9","sym
- **WARN** `BLACK:BTCUSD` (CRYPTO_CFD): master order rejected: HTTP 400 {"error":"insufficient free margin: required 1292.79, free 887.94","order":{"order_id":"ord_30ca8d536fbf2ca550","market_order_id":"ord_30ca8d536fbf2ca550","symb
- **FAIL** `BLACK:US500cash-1` (SPOT_INDICES): 2/10 followers did not copy correctly: f1 expected 4.0 got 0.0; f2 expected 4.0 got 0.0
- **WARN** `BLACK:GOLD.247` (CFD_247): master order rejected: HTTP 400 {"error":"insufficient free margin: required 7573.40, free 768.03","order":{"order_id":"ord_34d5e29ff33a0ee742","market_order_id":"ord_34d5e29ff33a0ee742","symb
- **WARN** `NSE:NIFTY` (IN_INDEX): master order rejected: HTTP 400 {"error":"insufficient free margin: required 5044.09, free 768.03","order":{"order_id":"ord_0ef7922d8f7884269b","market_order_id":"ord_0ef7922d8f7884269b","symb
- **WARN** `BSE:SENSEX 03DEC2026 76300 CE` (IN_OPTIONS): master order rejected: HTTP 400 {"error":"insufficient free margin: required 257054.00, free 28.39","order":{"order_id":"ord_2b9ad9f083e30afe8e","market_order_id":"ord_2b9ad9f083e30afe8e","sym
- **WARN** `BSE:SENSEX DEC2026 FUT` (IN_FUTURES): master order rejected: HTTP 400 {"error":"insufficient free margin: required 330164.00, free 28.39","order":{"order_id":"ord_5ae556361660456fd0","market_order_id":"ord_5ae556361660456fd0","sym
- **WARN** `GX:1!BANKNIFTY@FAIR` (GREEKS): master order rejected: HTTP 400 {"error":"insufficient free margin: required 123859.40, free 28.39","order":{"order_id":"ord_931a6fea19bdfce76d","market_order_id":"ord_931a6fea19bdfce76d","sym
- **WARN** `NSE:RELIANCE` (IN_STOCKS): master order rejected: HTTP 400 {"error":"insufficient free margin: required 545.68, free 28.39","order":{"order_id":"ord_ce0e4df8aa906bc8e3","market_order_id":"ord_ce0e4df8aa906bc8e3","symbol

Closed markets are SKIPPED, not failed: re-run during that market's session (Indian NSE/BSE 03:45-10:00 UTC, US stocks ~14:30-21:00 UTC, EU stocks 07:00-15:30 UTC).
