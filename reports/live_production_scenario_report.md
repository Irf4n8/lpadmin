# Live copy-trading scenario report

Evidence captured on 19 November 2026. The authenticated real hedging cohort comprised one master and ten B-book followers. All eleven started with zero positions and zero pending orders.

Case 62 passed. Three BTC master buys of 0.001 produced exactly one filled copy per originating order on each of ten followers. All three close requests returned HTTP 200 and all eleven accounts reported zero open positions afterward. Post-close pending orders and margin were not checked.

The public instance directory listed real-net. Its authenticated copy-link route returned HTTP 404, and position and order reads did not establish netting balances or exposure.

[Account preflight](evidence/live_scope_preflight.json) · [Case 62 order evidence](evidence/live_case62.json)

| ID | Scenario | Live verdict |
|---|---|---|
| 1 | Cancel and fill happen at the same time. | Not executed |
| 2 | A stop order’s trigger is moved twice during fast price action. | Not executed |
| 3 | A pending entry fills while its stop-loss is being edited. | Not executed |
| 4 | A breakout trade reverses before the opposite order is cancelled. | Not executed |
| 5 | A partial close and a stop-loss trigger overlap. | Not executed |
| 6 | The market moves before an order with protection is submitted. | Not executed |
| 7 | Followers use different sizing modes during a drawdown. | Not executed |
| 8 | A follower changes size with both a position and a pending order open. | Not executed |
| 9 | A small copy falls below the instrument’s minimum quantity. | Not executed |
| 10 | A follower enters zero when trying to cut exposure. | Not executed |
| 11 | One follower runs out of free margin halfway through a burst. | Not executed |
| 12 | A follower adds funds after missing an entry. | Not executed |
| 13 | A follower joins a master who already has a position and a pending entry. | Not executed |
| 14 | A follower unfollows with live exposure and then rejoins. | Not executed |
| 15 | A follower switches from hedging to netting with the same master. | Outside hedging-only scope |
| 16 | A follower’s manual trade looks identical to a copied trade. | Not executed |
| 17 | The follower and master close the same copied position almost simultaneously. | Not executed |
| 18 | A follower is disabled while carrying a copied position. | Not executed |
| 19 | A hedged portfolio looks flat in net quantity while both legs are open. | Not executed |
| 20 | A netting position reduces, flips and closes in quick succession. | Outside hedging-only scope |
| 21 | Netting followers receive a market entry, then the master adds protection. | Outside hedging-only scope |
| 22 | A pending limit fills and is closed quickly on netting. | Outside hedging-only scope |
| 23 | Normal and reverse followers hold opposite sides through a full trade. | Not executed |
| 24 | A busy master sends a long sequence of trades to 100 followers. | Not executed |
| 25 | The master exits and reverses while the original copies are still arriving. | Not executed |
| 26 | An order submission times out and the master retries. | Not executed |
| 27 | The master fills while some A-book followers face a routing rejection. | Not executed |
| 28 | One market closes while another keeps trading. | Not executed |
| 29 | The follower loses their connection while the master keeps trading. | Not executed |
| 30 | The platform goes down during a trade lifecycle. | Not executed |
| 31 | Close-all overlaps with individual closes during a selloff. | Not executed |
| 32 | Wi-Fi drops before the order leaves the device. | Not executed |
| 33 | The exit succeeds but the confirmation is lost. | Not executed |
| 34 | Position updates arrive out of order. | Not executed |
| 35 | The chart works while trading requests time out. | Not executed |
| 36 | Connectivity fails halfway through login. | Not executed |
| 37 | One device reconnects with stale settings. | Not executed |
| 38 | An unfollow confirmation is lost. | Not executed |
| 39 | History loads only partway over a slow connection. | Not executed |
| 40 | Only one group of users loses connectivity. | Not executed |
| 41 | Market-open login rush. | Not executed |
| 42 | Quiet baseline followed by a short trading burst. | Not executed |
| 43 | History traffic competes with exits. | Not executed |
| 44 | Sustained activity grows the history being read. | Not executed |
| 45 | Followers reconnect together. | Not executed |
| 46 | The slowest follower misses the headline result. | Not executed |
| 47 | A busy screen keeps polling during a quiet market. | Not executed |
| 48 | Returning users have very different history sizes. | Not executed |
| 49 | Rejected orders are mixed with accepted trades. | Not executed |
| 50 | Traffic stops while copies are still arriving. | Not executed |
| 51 | Two busy periods occur close together. | Not executed |
| 52 | A network timeout hides a successful JMeter request. | Not executed |
| 53 | An equity-based follower has a loss on a different symbol. | Not executed |
| 54 | A balance-based follower realizes a loss between entries. | Not executed |
| 55 | Reverse copying changes between two entries. | Not executed |
| 56 | Two identical pending tickets are edited independently. | Not executed |
| 57 | A pending copy becomes unaffordable before its trigger. | Not executed |
| 58 | Repeated partial closes reach the quantity step. | Not executed |
| 59 | A protected net position flips sides. | Outside hedging-only scope |
| 60 | A follower enters and exits at different prices from the master. | Not executed |
| 61 | A follower returns after several changes to the same symbol. | Not executed |
| 62 | One missing copy hides behind one duplicate. | Passed |
| 63 | Equal-size entries close in the wrong order. | Not executed |
| 64 | A closed trade’s stop hits its replacement. | Not executed |
| 65 | Two partial exits remove protection from the wrong leg. | Not executed |
| 66 | A stale reduce reaches a position that is already flat. | Not executed |
| 67 | One netting order crosses zero for only one follower. | Outside hedging-only scope |
| 68 | A net reversal books too much realized P&L. | Outside hedging-only scope |
| 69 | A replacement pending order inherits an old cancellation. | Not executed |
| 70 | A stop and a limit share a trigger price. | Not executed |
| 71 | Two protection edits overwrite different fields. | Not executed |
| 72 | A stop quantity survives a partial close at its original size. | Not executed |
| 73 | A follower misses an add but receives its close. | Not executed |
| 74 | A balance change is counted twice in equity sizing. | Not executed |
| 75 | An old exit is resized using a new multiplier. | Not executed |
| 76 | A rejected increase leaves funds reserved. | Not executed |
| 77 | Two instruments share a price level but use different quantity steps. | Not executed |
| 78 | A batch exit uses the wrong contract size. | Not executed |
| 79 | A follower switches accounts while an old positions request is outstanding. | Outside hedging-only scope |
| 80 | A copied close arrives after the follower reopens at a new ratio. | Not executed |
| 81 | JMeter records a successful read with stale trading data. | Not executed |
| 82 | A load run finishes flat despite missing whole round trips. | Passed at smoke load |
| 83 | A timeout during close makes the report count two exits. | Not executed |
| 84 | An aggregate copy count hides a mismatch between followers. | Passed at smoke load |
| 85 | A prior run makes a missing copy appear successful. | Passed at smoke load |

## Hedging follow-up

Ten linked 1× followers. All 14 selected [lifecycle checks](evidence/e2e_evidence_20261119_124800.md) passed. The [JMeter smoke workload](evidence/jmeter_real_evidence_20261119_124855.md) used two order threads, four 0.001 BTC entries and concurrent history, position and authentication traffic. All 266 HTTP samples succeeded. Cases 82, 84 and 85 passed at this scale. Each of the four new master IDs had one entry and one matched full exit per follower even with older same-size trades present. The post-load audit found zero open positions and zero stuck margin. [Order-level evidence](evidence/hedging_jmeter_current_ids.json)

The original audit counted filled exits sharing the entry reference as duplicates. The corrected audit identifies the opening ticket separately, and the transaction-level evidence above was rechecked. The lifecycle and JMeter checks overlap catalog scenarios and are counted separately.
