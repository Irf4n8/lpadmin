# Apache JMeter Load Test (standard)

**JMeter 5.6.3** | instance `paper` | 100 followers | 79s  
**HTML dashboard:** `C:\lpadmin\reports\jmeter\20261112_171139\html\index.html`

| Request | Result | Samples | Err % | p50 ms | p95 ms | p99 ms | TPS | SLA p95 |
| :--- | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Load: AUTH chart-token | ✅ | 60 | 0.0 | 56 | 76 | 93 | 5.71 | 2500 |
| Load: AUTH login | ✅ | 60 | 0.0 | 230 | 290 | 533 | 5.54 | 2500 |
| Validation: absurd tp/sl | ❌ | 1 | 100.0 | 118 | 118 | 118 | 1.0 | - |
| Validation: bad side | ✅ | 1 | 0.0 | 64 | 64 | 64 | 1.0 | - |
| Validation: missing symbol | ✅ | 1 | 0.0 | 55 | 55 | 55 | 1.0 | - |
| Validation: negative qty | ✅ | 1 | 0.0 | 64 | 64 | 64 | 1.0 | - |
| Validation: string qty | ✅ | 1 | 0.0 | 46 | 46 | 46 | 1.0 | - |
| Validation: unknown order type | ❌ | 1 | 100.0 | 80 | 80 | 80 | 1.0 | - |
| Validation: zero qty | ✅ | 1 | 0.0 | 93 | 93 | 93 | 1.0 | - |
| Load: ORDER close position | ✅ | 100 | 0.0 | 1075 | 1534 | 1559 | 4.93 | 5000 |
| Load: ORDER place market | ✅ | 100 | 0.0 | 1047 | 1498 | 1551 | 5.02 | 5000 |
| Load: READ orders (history) | ✅ | 15 | 0.0 | 369 | 525 | 525 | 1.63 | 6000 |
| Load: READ positions | ✅ | 3981 | 0.0 | 103 | 133 | 160 | 133.71 | 2500 |
| Integrity: no orphan positions / stuck margin after load | ❌ | - | - | - | - | - | - | - |

## Findings

- **Validation: absurd tp/sl** - KNOWN PLATFORM BUG - absurd TP/SL (tp=-1, sl=1e30) is accepted. got 200 Test failed: code expected to equal / received : [[[2]]]00 comparison: [[[4]]]00 /
- **Validation: unknown order type** - KNOWN PLATFORM BUG - unknown order type returns 500 instead of 400. got 500 Test failed: code expected to equal / received : [[[5]]]00 comparison: [[[4]]]00 /
- **Integrity: no orphan positions / stuck margin after load** - 2 accounts still hold 2 positions after the master closed everything; 2 with stuck margin; e.g. {'follower98@mailinator.com': 1, 'follower100@mailinator.com': 1}
