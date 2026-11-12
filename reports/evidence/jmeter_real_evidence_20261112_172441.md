# Apache JMeter Load Test (stress)

**JMeter 5.6.3** | instance `paper` | 100 followers | 142s  
**HTML dashboard:** `C:\lpadmin\reports\jmeter\20261112_172441\html\index.html`

| Request | Result | Samples | Err % | p50 ms | p95 ms | p99 ms | TPS | SLA p95 |
| :--- | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Load: AUTH chart-token | ✅ | 120 | 0.0 | 47 | 73 | 83 | 5.89 | 2500 |
| Load: AUTH login | ✅ | 120 | 0.0 | 212 | 250 | 485 | 5.8 | 2500 |
| Validation: absurd tp/sl | ❌ | 1 | 100.0 | 99 | 99 | 99 | 1.0 | - |
| Validation: bad side | ✅ | 1 | 0.0 | 46 | 46 | 46 | 1.0 | - |
| Validation: missing symbol | ✅ | 1 | 0.0 | 62 | 62 | 62 | 1.0 | - |
| Validation: negative qty | ✅ | 1 | 0.0 | 41 | 41 | 41 | 1.0 | - |
| Validation: string qty | ✅ | 1 | 0.0 | 40 | 40 | 40 | 1.0 | - |
| Validation: unknown order type | ❌ | 1 | 100.0 | 50 | 50 | 50 | 1.0 | - |
| Validation: zero qty | ✅ | 1 | 0.0 | 95 | 95 | 95 | 1.0 | - |
| Load: ORDER close position | ✅ | 200 | 0.0 | 1670 | 2160 | 2250 | 6.46 | 5000 |
| Load: ORDER place market | ✅ | 200 | 0.0 | 1664 | 2217 | 2309 | 6.56 | 5000 |
| Load: READ orders (history) | ✅ | 30 | 0.0 | 376 | 1018 | 1093 | 1.57 | 6000 |
| Load: READ positions | ✅ | 15583 | 0.0 | 108 | 145 | 186 | 260.53 | 2500 |
| Integrity: no orphan positions / stuck margin after load | ✅ | - | - | - | - | - | - | - |

## Findings

- **Validation: absurd tp/sl** - KNOWN PLATFORM BUG - absurd TP/SL (tp=-1, sl=1e30) is accepted. got 200 Test failed: code expected to equal / received : [[[2]]]00 comparison: [[[4]]]00 /
- **Validation: unknown order type** - KNOWN PLATFORM BUG - unknown order type returns 500 instead of 400. got 500 Test failed: code expected to equal / received : [[[5]]]00 comparison: [[[4]]]00 /
