# Apache JMeter Load Test (smoke)

**JMeter 5.6.3** | instance `paper` | 20 followers | 31s  
**HTML dashboard:** `C:\lpadmin\reports\jmeter\20261112_163508\html\index.html`

| Request | Result | Samples | Err % | p50 ms | p95 ms | p99 ms | TPS | SLA p95 |
| :--- | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Load: AUTH chart-token | ✅ | 10 | 0.0 | 45 | 75 | 75 | 3.68 | 2500 |
| Load: AUTH login | ✅ | 10 | 0.0 | 213 | 455 | 455 | 3.37 | 2500 |
| Validation: absurd tp/sl | ❌ | 1 | 100.0 | 99 | 99 | 99 | 1.0 | - |
| Validation: bad side | ✅ | 1 | 0.0 | 62 | 62 | 62 | 1.0 | - |
| Validation: missing symbol | ✅ | 1 | 0.0 | 36 | 36 | 36 | 1.0 | - |
| Validation: negative qty | ✅ | 1 | 0.0 | 38 | 38 | 38 | 1.0 | - |
| Validation: string qty | ✅ | 1 | 0.0 | 63 | 63 | 63 | 1.0 | - |
| Validation: unknown order type | ❌ | 1 | 100.0 | 61 | 61 | 61 | 1.0 | - |
| Validation: zero qty | ✅ | 1 | 0.0 | 190 | 190 | 190 | 1.0 | - |
| Load: ORDER close position | ✅ | 10 | 0.0 | 247 | 643 | 643 | 2.66 | 5000 |
| Load: ORDER place market | ✅ | 10 | 0.0 | 271 | 505 | 505 | 2.6 | 5000 |
| Load: READ orders (history) | ✅ | 4 | 0.0 | 276 | 363 | 363 | 2.02 | 6000 |
| Load: READ positions | ✅ | 428 | 0.0 | 103 | 133 | 208 | 29.05 | 2500 |
| Integrity: no orphan positions / stuck margin after load | ✅ | - | - | - | - | - | - | - |

## Findings

- **Validation: absurd tp/sl** - KNOWN PLATFORM BUG - absurd TP/SL (tp=-1, sl=1e30) is accepted. got 200 Test failed: code expected to equal / received : [[[2]]]00 comparison: [[[4]]]00 /
- **Validation: unknown order type** - KNOWN PLATFORM BUG - unknown order type returns 500 instead of 400. got 500 Test failed: code expected to equal / received : [[[5]]]00 comparison: [[[4]]]00 /
