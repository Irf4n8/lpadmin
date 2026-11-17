# Confirmed issues: how to reproduce (staging, Real / hedging)

Setup for all: master `ctmaster@mailinator.com`, followers `follower1..100@mailinator.com`, all linked on `real` at multiplier 2.
Run the scripted versions with `.venv/bin/python <script> --i-understand-real-money` (the first two need no flag).

## 1. Order-count mismatch at ~200 orders
Script: `python test_suite/order_count_parity_runner.py --instance real --orders 200 --threads 1 --delay 1 --pattern buy --multiplier 2 --i-understand-real-money`

Steps: master places 200 market BUY 0.001 BTCUSDT.P orders, 1 s apart. Wait ~2 min. Compare each follower's order list with the master's (`copy_ref` of a follower order = `-<master order_id>`).

Result (2026-11-16 17:17): master accepted 196/200 (4 refused, "liquidity provider must be configured, enabled and tested"). Every master order that was accepted and filled should exist on all 100 followers; 4 of them are missing on some followers: one master order missing on 96/100 followers, one on 67, one on 15, one on 1. Only 4/100 followers match the master. Size of copies that do arrive is exactly 2.0x. Evidence: `reports/evidence/order_parity_real_20261116_171732.json`.
Earlier runs: 188/200 (3 missing), 196/200 (4 missing), netting 199/200 (2 missing). 10-order run passes. A netting run of 100 BUY then 100 SELL at 1 s gaps passed.

## 2. Multiplier 0 is silently stored as 1x
`POST /v1/oms/real/copy/follow` as a follower, body `{"master_client_id":"<master>","method":"multiplier","multiplier":0}`
Response 200, stored `multiplier: 1`. Same call with `-1` returns 400 "The multiplier can't be below 0.01." (0 should be rejected the same way).

## 3. No minimum order size; copy is rounded UP
`POST /v1/oms/real/orders` as master, body `{"symbol":"BINANCE:BTCUSDT.P","side":"BUY","type":"MARKET","qty":0.0001}`
Master order is accepted and FILLED at 0.0001. The follower (2x) receives 0.001 instead of 0.0002, i.e. 5x too large.

## 4. STOP order edit: `price` keeps the old value
Place a STOP at P, then `PUT /v1/oms/real/orders/<order_id>/modify` with `{"trigger_price": P+100}`. The order shows `price: P` (old) and `trigger_price: P+100`. Followers' copies move correctly. A UI reading `price` shows the old trigger.

## 5. Unfollow then follow again keeps old history
As a follower: trade, `POST /v1/oms/real/copy/unfollow`, then `POST /v1/oms/real/copy/follow` again. Orders, trade history and realized P&L are unchanged (e.g. 200 history rows, 3596 orders, P&L -51.03 before and after).

Scripted: `python test_suite/repro_known_issues.py` (items 2 to 5). Evidence: `reports/evidence/repro_known_issues.json`.

## 6. Pending-order edit: unknown field names are accepted and silently ignored
Script: `python test_suite/pending_edit_runner.py` (add `--all` for 100 followers).
Place a LIMIT or STOP, then `PUT /v1/oms/real/orders/<id>/modify`:
- `{"price": X}` and `{"trigger_price": X}` both move the order (LIMIT and STOP, BUY and SELL).
- `{"new_price": X}`, `{"stop_price": X}`, `{"newPrice": X}` return HTTP 200 and change nothing.
A client that sends the wrong key sees success while the trigger stays where it was.
For STOP orders only `trigger_price` changes; the `price` field keeps the original value on the master and on every follower copy.
