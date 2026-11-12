# Apache JMeter Load Test (standard)

**JMeter 5.6.3** | instance `paper` | 100 followers | 19s  
**HTML dashboard:** `C:\lpadmin\reports\jmeter\20261112_163606\html\index.html`

| Request | Result | Samples | Err % | p50 ms | p95 ms | p99 ms | TPS | SLA p95 |
| :--- | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Load: AUTH chart-token | ✅ | 60 | 0.0 | 44 | 69 | 76 | 5.69 | 2500 |
| Load: AUTH login | ✅ | 60 | 0.0 | 210 | 242 | 494 | 5.55 | 2500 |
| Load: ORDER close position | ✅ | 36 | 0.0 | 211 | 431 | 432 | 6.82 | 5000 |
| Load: ORDER place market | ✅ | 41 | 0.0 | 225 | 418 | 446 | 7.4 | 5000 |
| Integrity: no orphan positions / stuck margin after load | ❌ | - | - | - | - | - | - | - |

## Findings

- **Integrity: no orphan positions / stuck margin after load** - 101 accounts still hold 101 positions after the master closed everything; 101 with stuck margin; e.g. {'ctmaster@mailinator.com': 1, 'follower1@mailinator.com': 1, 'follower6@mailinator.com': 1}
