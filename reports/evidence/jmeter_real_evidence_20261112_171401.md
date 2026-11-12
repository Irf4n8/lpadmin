# Apache JMeter Load Test (standard)

**JMeter 5.6.3** | instance `paper` | 100 followers | 75s  
**HTML dashboard:** `C:\lpadmin\reports\jmeter\20261112_171401\html\index.html`

| Request | Result | Samples | Err % | p50 ms | p95 ms | p99 ms | TPS | SLA p95 |
| :--- | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Load: AUTH chart-token | ✅ | 60 | 0.0 | 49 | 72 | 76 | 5.75 | 2500 |
| Load: AUTH login | ✅ | 60 | 0.0 | 218 | 259 | 579 | 5.57 | 2500 |
| Validation: absurd tp/sl | ❌ | 1 | 100.0 | 333 | 333 | 333 | 1.0 | - |
| Validation: bad side | ✅ | 1 | 0.0 | 63 | 63 | 63 | 1.0 | - |
| Validation: missing symbol | ✅ | 1 | 0.0 | 72 | 72 | 72 | 1.0 | - |
| Validation: negative qty | ✅ | 1 | 0.0 | 65 | 65 | 65 | 1.0 | - |
| Validation: string qty | ✅ | 1 | 0.0 | 71 | 71 | 71 | 1.0 | - |
| Validation: unknown order type | ❌ | 1 | 100.0 | 56 | 56 | 56 | 1.0 | - |
| Validation: zero qty | ✅ | 1 | 0.0 | 102 | 102 | 102 | 1.0 | - |
| Load: ORDER close position | ✅ | 100 | 0.0 | 572 | 964 | 1148 | 6.28 | 5000 |
| Load: ORDER place market | ✅ | 100 | 0.0 | 557 | 959 | 1425 | 6.29 | 5000 |
| Load: READ orders (history) | ✅ | 15 | 0.0 | 452 | 668 | 668 | 1.6 | 6000 |
| Load: READ positions | ✅ | 3950 | 0.0 | 105 | 137 | 170 | 132.48 | 2500 |
| Integrity: no orphan positions / stuck margin after load | ❌ | - | - | - | - | - | - | - |

## Findings

- **Validation: absurd tp/sl** - KNOWN PLATFORM BUG - absurd TP/SL (tp=-1, sl=1e30) is accepted. got 200 Test failed: code expected to equal / received : [[[2]]]00 comparison: [[[4]]]00 /
- **Validation: unknown order type** - KNOWN PLATFORM BUG - unknown order type returns 500 instead of 400. got 500 Test failed: code expected to equal / received : [[[5]]]00 comparison: [[[4]]]00 /
- **Integrity: no orphan positions / stuck margin after load** - 22 accounts still hold 22 positions after the master closed everything; 22 with stuck margin; e.g. {'follower33@mailinator.com': 1, 'follower31@mailinator.com': 1, 'follower38@mailinator.com': 1}
