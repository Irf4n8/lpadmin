# Apache JMeter Load Test (stress)

**JMeter 5.6.3** | instance `paper` | 100 followers | 154s  
**HTML dashboard:** `C:\lpadmin\reports\jmeter\20261113_094055\html\index.html`

| Request | Result | Samples | Err % | p50 ms | p95 ms | p99 ms | TPS | SLA p95 |
| :--- | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Load: AUTH chart-token | ✅ | 120 | 0.0 | 53 | 80 | 100 | 5.9 | 2500 |
| Load: AUTH login | ✅ | 120 | 0.0 | 215 | 260 | 300 | 5.81 | 2500 |
| Validation: absurd tp/sl | ❌ | 1 | 100.0 | 113 | 113 | 113 | 1.0 | - |
| Validation: bad side | ✅ | 1 | 0.0 | 55 | 55 | 55 | 1.0 | - |
| Validation: missing symbol | ✅ | 1 | 0.0 | 61 | 61 | 61 | 1.0 | - |
| Validation: negative qty | ✅ | 1 | 0.0 | 83 | 83 | 83 | 1.0 | - |
| Validation: string qty | ✅ | 1 | 0.0 | 73 | 73 | 73 | 1.0 | - |
| Validation: unknown order type | ❌ | 1 | 100.0 | 263 | 263 | 263 | 1.0 | - |
| Validation: zero qty | ✅ | 1 | 0.0 | 127 | 127 | 127 | 1.0 | - |
| Load: ORDER close position | ✅ | 200 | 0.0 | 496 | 678 | 791 | 8.57 | 5000 |
| Load: ORDER place market | ✅ | 200 | 0.0 | 510 | 714 | 775 | 8.51 | 5000 |
| Load: READ orders (history) | ❌ | 30 | 0.0 | 2273 | 12760 | 14442 | 0.85 | 6000 |
| Load: READ positions | ✅ | 13593 | 0.0 | 106 | 396 | 1550 | 227.21 | 2500 |
| Integrity: no orphan positions / stuck margin after load | ✅ | - | - | - | - | - | - | - |

## Findings

- **Validation: absurd tp/sl** - KNOWN PLATFORM BUG - absurd TP/SL (tp=-1, sl=1e30) is accepted. got 200 Test failed: code expected to equal / received : [[[2]]]00 comparison: [[[4]]]00 /
- **Validation: unknown order type** - KNOWN PLATFORM BUG - unknown order type returns 500 instead of 400. got 500 Test failed: code expected to equal / received : [[[5]]]00 comparison: [[[4]]]00 /
- **Load: READ orders (history)** - p95 12760ms > SLA 6000ms
