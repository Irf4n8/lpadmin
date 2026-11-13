# Bug report - lpadmin.blackfx.com (tested 2026-11-13)

Written in simple steps. Every command can be copied and pasted into a terminal that has `curl` (Git Bash on Windows works).
Use a TEST trader account (not a real client). Replace the three values in angle brackets.

**Fastest way to reproduce BUG-1, BUG-2 and BUG-3:** `python scripts/repro_bugs.py` (one command, prints each result, cleans up). BUG-4/5 need the setup below.

**Videos of each bug** (recorded live, `reports/videos/`; regenerate with `python scripts/record_bug_videos.py`; play in Chrome/Edge/VLC):
* `BUG-1_orders-history-no-paging.webm` - `BUG-2_wrong-order-type-returns-500.webm` - `BUG-3_invalid-TP-SL-silently-dropped.webm`
* `BUG-3_in-the-real-trading-terminal.webm` - the real web terminal showing the new position with SL/TP empty
* BUG-4 / BUG-5 (`real-net`): no video yet - blocked while the master is A-book.

## Step 0 - get a login token (needed for every bug below)

```bash
# 0.1  log in (this saves a session cookie in a file called cj.txt)
curl -s -c cj.txt -X POST https://lpadmin.blackfx.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"<trader email>","password":"<password>"}'
# you should see a JSON reply with success/ok

# 0.2  turn the session into a Bearer token (copy the "token" value from the reply)
curl -s -b cj.txt -X POST https://lpadmin.blackfx.com/api/auth/chart-token
# reply looks like: {"token":"xxxxxxxx...", ...}

# 0.3  keep it in a variable so the next commands are short
TOKEN="<paste the token here>"
```

Every command below uses the header `Authorization: Bearer $TOKEN`.

---

## BUG-1 - Orders history has no paging: every call returns the whole history (4 MB+), which slows the platform under heavy load
**Severity:** Low-Medium (performance risk, grows over time)  **Where:** `GET /v1/oms/{instance}/orders`

**What is wrong (simple):** this call returns EVERY order the account ever made, in one go, with no page size. The test accounts now hold 10,000-13,000 orders, so each call sends about 4 MB. On a quiet platform that still answers in about 1 second, so ONE call does not look slow. It becomes slow only when many users are active at the same time (heavy trading + many readers), and it gets worse every day as history grows.

**Steps to reproduce (1 - the size, always visible)**
1. Do Step 0 with an account that has many orders (e.g. the master).
2. Run:
```bash
curl -s -o /dev/null -w "HTTP %{http_code}  size %{size_download} bytes  time %{time_total}s\n" \
  https://lpadmin.blackfx.com/v1/oms/paper/orders \
  -H "Authorization: Bearer $TOKEN" -H "X-Broker-ID: paper"
```
   Measured 2026-11-13: HTTP 200, 12,919 orders, 4,482,138 bytes, 0.92 s. There is no `limit`/`offset` option to make it smaller.

**Steps to reproduce (2 - the slowdown, needs load; this is what failed our limit)**
1. From the project folder run `python test_suite/jmeter_real_runner.py --profile standard` (or `--profile stress`). It runs about 50 users trading and reading at once.
2. Open the result table and read the row **READ orders (history)**.

**Actual result**
* Under heavy mixed load (JMeter): p95 = **6,740 ms** (standard) and **12,760 ms** (stress). Our limit is 6,000 ms.
* Reading alone on a quiet platform (20 users at once, measured 2026-11-13): p95 about 3.1 s - inside the limit. So you will NOT see the failure with a few curl calls.

**Expected result:** a paged response (for example `?limit=100&offset=0`, with a sensible default) so the size and time do not grow with history, and the 6 s limit holds under load.

**Proof files:** `reports/evidence/jmeter_real_evidence_20261113_093842.md` (standard), `reports/evidence/jmeter_real_evidence_20261113_094055.md` (stress), HTML graphs in `reports/jmeter/20261113_093842/html/index.html`.

---

## BUG-2 - Wrong order type returns a server error (HTTP 500) instead of a normal 400 message
**Severity:** Low-Medium  **Where:** `POST /v1/oms/{instance}/orders`

**What is wrong (simple):** this endpoint only fills MARKET orders. If you send any other type (for example "WEIRD", or LIMIT/STOP), it answers with HTTP **500** (a server-error code) and a text message, instead of HTTP **400** (a bad-request code). A 500 normally means "the server crashed", so monitoring and client apps treat it as a platform fault. Other bad input (wrong side, zero quantity) correctly returns 400.

**Steps to reproduce** (re-checked live 2026-11-13)
1. Do Step 0.
2. Send an order with an unsupported type:
```bash
curl -s -w "\nHTTP %{http_code}\n" -X POST https://lpadmin.blackfx.com/v1/oms/paper/orders \
  -H "Authorization: Bearer $TOKEN" -H "X-Broker-ID: paper" -H "Content-Type: application/json" \
  -d '{"symbol":"BINANCE:BTCUSDT.P","side":"BUY","type":"WEIRD","qty":1}'
```
3. Compare with a wrong side (this one is handled correctly):
```bash
curl -s -w "\nHTTP %{http_code}\n" -X POST https://lpadmin.blackfx.com/v1/oms/paper/orders \
  -H "Authorization: Bearer $TOKEN" -H "X-Broker-ID: paper" -H "Content-Type: application/json" \
  -d '{"symbol":"BINANCE:BTCUSDT.P","side":"SIDEWAYS","type":"MARKET","qty":1}'
```

**Actual result**
* Step 2: `HTTP 500` with `{"error":"this endpoint fills at MARKET; for a WEIRD order POST to /orders/pending"}`
* Step 3: `HTTP 400` with `{"error":"symbol, side (BUY/SELL) and a positive qty are required"}`

**Expected result:** step 2 should also be `HTTP 400` (the message text is fine). No order is created in either case.

Note for whoever tests it: it is only a **status-code** problem. The message is helpful and nothing is traded, so it can look "fine" if you only read the text. Look at the HTTP code (`-w "%{http_code}"`).

**Proof files:** row "Validation: unknown order type" in both JMeter evidence files; scenario B8 in `reports/evidence/breakpoint_race_evidence_20261113_100538.md`.

---

## BUG-3 - A new order with invalid TP/SL is accepted (HTTP 200) and the TP/SL are silently thrown away, so the trade has NO protection
**Severity:** Medium  **Where:** `POST /v1/oms/{instance}/orders` (the TP/SL fields on a new order)

**What is wrong (simple):** when you open a trade and attach a take-profit / stop-loss that makes no sense (negative, or on the wrong side of the price), the platform does not refuse it. It says "200 OK", opens the trade, and quietly DROPS the TP/SL. The user thinks the trade is protected, but it is not. The separate "set TP/SL on an open position" call does reject the same values with a clear 400 message, so the two paths behave differently.

(Correction to an earlier version of this report: I first wrote that the impossible values were stored on the position. Re-testing showed they are NOT stored; they are discarded. That is a different and arguably worse problem: silent loss of protection.)

**Steps to reproduce** (re-checked live 2026-11-13, on a test account with no copy link)
1. Do Step 0.
2. Open a small BUY with TP = -1 and SL = 1e30:
```bash
curl -s -w "\nHTTP %{http_code}\n" -X POST https://lpadmin.blackfx.com/v1/oms/paper/orders \
  -H "Authorization: Bearer $TOKEN" -H "X-Broker-ID: paper" -H "Content-Type: application/json" \
  -d '{"symbol":"BINANCE:BTCUSDT.P","side":"BUY","type":"MARKET","qty":0.01,"tp":-1,"sl":1e30}'
```
3. Look at the open position:
```bash
curl -s https://lpadmin.blackfx.com/v1/oms/paper/positions -H "Authorization: Bearer $TOKEN" -H "X-Broker-ID: paper"
```
   The new position is there, and `tp_order` and `sl_order` are `null`.
4. For comparison, send a VALID TP/SL on a new order (BUY: TP above the price, SL below, e.g. price 68500 -> `"tp":75000,"sl":62000`). Step 3 now shows both values stored. So TP/SL on orders work; only invalid ones vanish silently.
5. Compare with the dedicated call on an open position (it behaves correctly):
```bash
curl -s -w "\nHTTP %{http_code}\n" -X PUT https://lpadmin.blackfx.com/v1/oms/paper/positions/<market_order_id>/protection \
  -H "Authorization: Bearer $TOKEN" -H "X-Broker-ID: paper" -H "Content-Type: application/json" \
  -d '{"tp":-1,"sl":1e30}'
```
   -> `HTTP 400 {"error":"SL crosses current price"}`.
6. CLEAN UP: close the position with `POST /v1/oms/paper/positions/<market_order_id>/squareoff` and body `{}`.

**Actual results (all measured 2026-11-13)**
| Sent on a new BUY order | HTTP | Stored on the position |
| --- | --- | --- |
| tp = -1 | 200 | nothing |
| sl = 1e30 | 200 | nothing |
| tp = -1 and sl = 1e30 | 200 | nothing |
| TP below price and SL above price (wrong sides) | 200 | nothing |
| tp = 0 and sl = 0 | 200 | sl stored as 0, tp dropped |
| tp = 1e30 (huge, but on the profit side) | 200 | tp = 1e+30 stored |
| valid TP above / SL below | 200 | both stored |

**Expected result:** an order carrying an invalid TP/SL is rejected with `HTTP 400` and a clear message (same rule as the protection call: TP above the price and SL below it for a BUY, both positive and in a sane range), and no trade is opened. At the very least the reply must say that the TP/SL was ignored.

**Proof files:** row "Validation: absurd tp/sl" in both JMeter evidence files; "INVALID input ACCEPTED (200)" in scenario B8 of `reports/evidence/breakpoint_race_evidence_20261113_100538.md`.

---

## BUG-4 and BUG-5 - Netting account (`real-net`): TP/SL and pending orders are NOT copied to followers
**Status of verification:** reproduced 3 times on 2026-11-13 (twice with the suite, once with a standalone probe, 30-second waits). NOT re-run during the later "cannot be reproduced" check: my safety guard blocks real-instance runs while the master is A-book, and I did not override it. If these two cannot be reproduced on your side, first check the SETUP below, because this bug needs real-net follow links and funded real-net wallets; with no links nothing is copied on any instance.

**Severity:** High (both)  **Where:** the copy-trading engine on the netting instance `real-net`

**What is wrong (simple):**
* BUG-4: the master sets Take-Profit/Stop-Loss on a trade. On the hedging instance (`real`) every follower gets the same TP/SL. On the netting instance (`real-net`) **no follower gets it**.
* BUG-5: the master places a pending (limit) order. On `real` every follower gets a pending order. On `real-net` **no follower gets one**, so they miss the trade when the price arrives.
Opening, adding, reducing, flipping and closing positions ARE copied correctly on `real-net`; only these two things are missing.

### Setup (once) - needs 2+ TEST accounts: one master and followers
Important: a follower has only ONE link per master. Using `follow` on a follower that already follows on another instance CONVERTS that link, and a later unfollow ENDS it (paper links cannot be recreated). So use followers that have NO active link. Also use B-book test accounts only - A-book orders can reach a real broker.

A. Give the master and each follower money on the netting wallet (admin action - log in as admin first):
```bash
ADMIN_TOKEN=$(curl -s -X POST https://lpadmin.blackfx.com/admin/api/login -H "Content-Type: application/json" \
  -d '{"email":"<admin email>","password":"<admin password>","remember":true}' | python -c "import sys,json;print(json.load(sys.stdin)['token'])")
# for the master and for each follower (member_id is in GET /admin/api/members):
curl -s -X POST https://lpadmin.blackfx.com/admin/api/members/<member_id>/balance \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"instance":"real-net","balance":1000000,"remark":"bug repro","force":true}'
```
B. Make each follower copy the master on `real-net` (log in as the FOLLOWER with Step 0, then):
```bash
curl -s -X POST https://lpadmin.blackfx.com/v1/oms/real-net/copy/follow \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"master_client_id":"<master member id, e.g. mem_aac4ca423a6925dca7>","method":"multiplier","multiplier":1,"reverse":false,"copy_mode":"public"}'
```
   (In the web terminal: Copy trading tab, choose "Real (Netting)", press Follow next to the master.)

Keep the master's token in `MTOKEN` and one follower's token in `FTOKEN` (Step 0 for each).

### BUG-4 steps - TP/SL not copied
1. Master buys 0.2 ETH on the netting instance:
```bash
curl -s -X POST https://lpadmin.blackfx.com/v1/oms/real-net/orders \
  -H "Authorization: Bearer $MTOKEN" -H "X-Broker-ID: real-net" -H "Content-Type: application/json" \
  -d '{"symbol":"BINANCE:ETHUSDT.P","side":"BUY","type":"MARKET","qty":0.2}'
```
   Copy `market_order_id` and the fill price from the reply.
2. Wait 5 seconds. A follower now has the position (check: `curl -s https://lpadmin.blackfx.com/v1/oms/real-net/positions -H "Authorization: Bearer $FTOKEN" -H "X-Broker-ID: real-net"`). This part works.
3. Master sets TP 10% above and SL 10% below the entry price (example: entry 1900, TP 2090, SL 1710):
```bash
curl -s -X PUT https://lpadmin.blackfx.com/v1/oms/real-net/positions/<market_order_id>/protection \
  -H "Authorization: Bearer $MTOKEN" -H "X-Broker-ID: real-net" -H "Content-Type: application/json" \
  -d '{"tp":2090,"sl":1710}'
```
   Reply is HTTP 200; the master's own position now shows both values.
4. Wait 30 seconds, then read a follower's position again (same command as step 2) and look at `tp_order` and `sl_order`.
5. Compare: repeat steps 1-4 on `real` (hedging) - the follower's `tp_order.trigger_price` and `sl_order.trigger_price` are filled in.

**Actual result:** on `real-net` the follower's `tp_order` and `sl_order` stay empty (tested on 6 of 6 followers, waited 30 s). Master has both.
**Expected result:** every follower's position gets the master's TP and SL within a few seconds, exactly like on `real`.

### BUG-5 steps - pending orders not copied
1. Master places a BUY LIMIT about 20% below the current price (example: price 1900, limit 1520):
```bash
curl -s -X POST https://lpadmin.blackfx.com/v1/oms/real-net/orders/pending \
  -H "Authorization: Bearer $MTOKEN" -H "X-Broker-ID: real-net" -H "Content-Type: application/json" \
  -d '{"symbol":"BINANCE:ETHUSDT.P","side":"BUY","type":"LIMIT","qty":0.1,"price":1520}'
```
   Reply is HTTP 200 and the order state is `PENDING` on the master.
2. Wait 30 seconds, then list a follower's orders:
```bash
curl -s https://lpadmin.blackfx.com/v1/oms/real-net/orders -H "Authorization: Bearer $FTOKEN" -H "X-Broker-ID: real-net"
```
   Look for an order with `"state":"PENDING"` on that symbol.
3. Compare: repeat on `real` - every follower has the pending order.
4. CLEAN UP: cancel the master's order (`DELETE /v1/oms/real-net/orders/<order_id>` with the master token), close any positions, and end the test links.

**Actual result:** on `real-net` the follower has no pending order (only older FILLED market orders).
**Expected result:** each follower gets a pending order of master quantity x follower multiplier at the same price; cancelling on the master removes them.

**One-command version (our test tool does all the setup, runs, and cleans up):**
`python scratch/probe/netprobe2.py real-net` (section A = BUG-4, section B = BUG-5), or
`python test_suite/netting_hedging_runner.py --instances real-net --followers 6 --only N5,P1`.
It refuses to run while the master is A-book.

**Proof files:** `reports/evidence/netting_hedging_evidence_20261113_101948.md` (scenarios N5 and P1). Reproduced twice with the full test and once with the standalone probe using 30-second waits, so it is not a timing issue.
