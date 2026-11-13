# Apache JMeter Load Test (standard)

**JMeter 5.6.3** | instance `paper` | 100 followers | 87s  
**HTML dashboard:** `C:\lpadmin\reports\jmeter\20261113_093842\html\index.html`

| Request | Result | Samples | Err % | p50 ms | p95 ms | p99 ms | TPS | SLA p95 |
| :--- | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Load: AUTH chart-token | ✅ | 60 | 0.0 | 53 | 77 | 79 | 5.79 | 2500 |
| Load: AUTH login | ✅ | 60 | 0.0 | 207 | 243 | 603 | 5.57 | 2500 |
| Validation: absurd tp/sl | ❌ | 1 | 100.0 | 107 | 107 | 107 | 1.0 | - |
| Validation: bad side | ✅ | 1 | 0.0 | 66 | 66 | 66 | 1.0 | - |
| Validation: missing symbol | ✅ | 1 | 0.0 | 63 | 63 | 63 | 1.0 | - |
| Validation: negative qty | ✅ | 1 | 0.0 | 40 | 40 | 40 | 1.0 | - |
| Validation: string qty | ✅ | 1 | 0.0 | 39 | 39 | 39 | 1.0 | - |
| Validation: unknown order type | ❌ | 1 | 100.0 | 44 | 44 | 44 | 1.0 | - |
| Validation: zero qty | ✅ | 1 | 0.0 | 84 | 84 | 84 | 1.0 | - |
| Load: ORDER close position | ✅ | 100 | 0.0 | 449 | 907 | 1031 | 6.77 | 5000 |
| Load: ORDER place market | ✅ | 100 | 0.0 | 661 | 1436 | 1849 | 6.55 | 5000 |
| Load: READ orders (history) | ❌ | 15 | 0.0 | 2359 | 6740 | 6740 | 1.01 | 6000 |
| Load: READ positions | ✅ | 2719 | 0.0 | 108 | 1116 | 2216 | 91.25 | 2500 |
| Integrity: no orphan positions / stuck margin after load | ✅ | - | - | - | - | - | - | - |

## Findings

- **Validation: absurd tp/sl** - KNOWN PLATFORM BUG - absurd TP/SL (tp=-1, sl=1e30) is accepted. got 200 Test failed: code expected to equal / received : [[[2]]]00 comparison: [[[4]]]00 /
- **Validation: unknown order type** - KNOWN PLATFORM BUG - unknown order type returns 500 instead of 400. got 500 Test failed: code expected to equal / received : [[[5]]]00 comparison: [[[4]]]00 /
- **Load: READ orders (history)** - p95 6740ms > SLA 6000ms
