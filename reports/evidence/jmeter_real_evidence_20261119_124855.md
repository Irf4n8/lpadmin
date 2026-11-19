# Apache JMeter Load Test (smoke)

**JMeter 5.6.3** | instance `real` | 10 followers | 29s  
**HTML dashboard:** `/Users/irf4n/Copy Trading/lpadmin/reports/jmeter/20261119_124855/html/index.html`

| Request | Result | Samples | Err % | p50 ms | p95 ms | p99 ms | TPS | SLA p95 |
| :--- | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Load: AUTH chart-token | ✅ | 10 | 0.0 | 71 | 1265 | 1265 | 3.46 | 2500 |
| Load: AUTH login | ✅ | 10 | 0.0 | 369 | 748 | 748 | 3.25 | 2500 |
| Load: ORDER close position | ✅ | 4 | 0.0 | 78 | 103 | 103 | 2.33 | 5000 |
| Load: ORDER place market | ✅ | 4 | 0.0 | 144 | 555 | 555 | 1.88 | 5000 |
| Load: READ orders (history) | ✅ | 4 | 0.0 | 667 | 1769 | 1769 | 1.15 | 6000 |
| Load: READ positions | ✅ | 234 | 0.0 | 170 | 1121 | 3731 | 15.82 | 2500 |
| Integrity: no orphan positions / stuck margin after load | ✅ | - | - | - | - | - | - | - |

## Findings

