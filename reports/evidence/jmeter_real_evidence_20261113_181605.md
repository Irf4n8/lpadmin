# Apache JMeter Load Test (standard)

**JMeter 5.6.3** | instance `paper` | 100 followers | 67s  
**HTML dashboard:** `/Users/irf4n/Copy Trading/lpadmin/reports/jmeter/20261113_181605/html/index.html`

| Request | Result | Samples | Err % | p50 ms | p95 ms | p99 ms | TPS | SLA p95 |
| :--- | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Load: AUTH chart-token | ✅ | 60 | 0.0 | 48 | 75 | 237 | 5.64 | 2500 |
| Load: AUTH login | ✅ | 60 | 0.0 | 198 | 246 | 308 | 5.58 | 2500 |
| Validation: absurd tp/sl | ❌ | 1 | 100.0 | 68 | 68 | 68 | 1.0 | - |
| Validation: bad side | ✅ | 1 | 0.0 | 64 | 64 | 64 | 1.0 | - |
| Validation: missing symbol | ✅ | 1 | 0.0 | 49 | 49 | 49 | 1.0 | - |
| Validation: negative qty | ✅ | 1 | 0.0 | 46 | 46 | 46 | 1.0 | - |
| Validation: string qty | ✅ | 1 | 0.0 | 43 | 43 | 43 | 1.0 | - |
| Validation: unknown order type | ❌ | 1 | 100.0 | 46 | 46 | 46 | 1.0 | - |
| Validation: zero qty | ✅ | 1 | 0.0 | 116 | 116 | 116 | 1.0 | - |
| Load: ORDER close position | ✅ | 100 | 0.0 | 45 | 72 | 90 | 8.53 | 5000 |
| Load: ORDER place market | ✅ | 100 | 0.0 | 95 | 120 | 128 | 8.52 | 5000 |
| Load: READ orders (history) | ✅ | 15 | 0.0 | 381 | 1494 | 1494 | 1.46 | 6000 |
| Load: READ positions | ✅ | 4139 | 0.0 | 95 | 135 | 161 | 138.93 | 2500 |
| Integrity: no orphan positions / stuck margin after load | ✅ | - | - | - | - | - | - | - |

## Findings

- **Validation: absurd tp/sl** - KNOWN PLATFORM BUG - absurd TP/SL (tp=-1, sl=1e30) is accepted. got 200 Test failed: code expected to equal / received : [[[2]]]00 comparison: [[[4]]]00 /
- **Validation: unknown order type** - KNOWN PLATFORM BUG - unknown order type returns 500 instead of 400. got 500 Test failed: code expected to equal / received : [[[5]]]00 comparison: [[[4]]]00 /
