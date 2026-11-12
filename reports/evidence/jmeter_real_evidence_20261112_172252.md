# Apache JMeter Load Test (standard)

**JMeter 5.6.3** | instance `paper` | 100 followers | 75s  
**HTML dashboard:** `C:\lpadmin\reports\jmeter\20261112_172252\html\index.html`

| Request | Result | Samples | Err % | p50 ms | p95 ms | p99 ms | TPS | SLA p95 |
| :--- | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Load: AUTH chart-token | ✅ | 60 | 0.0 | 46 | 71 | 77 | 5.73 | 2500 |
| Load: AUTH login | ✅ | 60 | 0.0 | 220 | 275 | 507 | 5.57 | 2500 |
| Validation: absurd tp/sl | ❌ | 1 | 100.0 | 106 | 106 | 106 | 1.0 | - |
| Validation: bad side | ✅ | 1 | 0.0 | 39 | 39 | 39 | 1.0 | - |
| Validation: missing symbol | ✅ | 1 | 0.0 | 61 | 61 | 61 | 1.0 | - |
| Validation: negative qty | ✅ | 1 | 0.0 | 58 | 58 | 58 | 1.0 | - |
| Validation: string qty | ✅ | 1 | 0.0 | 38 | 38 | 38 | 1.0 | - |
| Validation: unknown order type | ❌ | 1 | 100.0 | 43 | 43 | 43 | 1.0 | - |
| Validation: zero qty | ✅ | 1 | 0.0 | 103 | 103 | 103 | 1.0 | - |
| Load: ORDER close position | ✅ | 100 | 0.0 | 839 | 1380 | 1485 | 5.85 | 5000 |
| Load: ORDER place market | ✅ | 100 | 0.0 | 795 | 1374 | 1423 | 5.82 | 5000 |
| Load: READ orders (history) | ✅ | 15 | 0.0 | 342 | 401 | 401 | 1.64 | 6000 |
| Load: READ positions | ✅ | 4024 | 0.0 | 98 | 126 | 172 | 135.03 | 2500 |
| Integrity: no orphan positions / stuck margin after load | ✅ | - | - | - | - | - | - | - |

## Findings

- **Validation: absurd tp/sl** - KNOWN PLATFORM BUG - absurd TP/SL (tp=-1, sl=1e30) is accepted. got 200 Test failed: code expected to equal / received : [[[2]]]00 comparison: [[[4]]]00 /
- **Validation: unknown order type** - KNOWN PLATFORM BUG - unknown order type returns 500 instead of 400. got 500 Test failed: code expected to equal / received : [[[5]]]00 comparison: [[[4]]]00 /
