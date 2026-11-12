# Apache JMeter Load Test (smoke)

**JMeter 5.6.3** | instance `paper` | 20 followers | 30s  
**HTML dashboard:** `C:\lpadmin\reports\jmeter\20261112_163405\html\index.html`

| Request | Result | Samples | Err % | p50 ms | p95 ms | p99 ms | TPS | SLA p95 |
| :--- | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Load: AUTH chart-token | ✅ | 10 | 0.0 | 60 | 70 | 70 | 3.87 | 2500 |
| Load: AUTH login | ✅ | 10 | 0.0 | 213 | 616 | 616 | 3.33 | 2500 |
| Validation: absurd tp/sl | ❌ | 1 | 100.0 | 93 | 93 | 93 | 1.0 | - |
| Validation: bad side | ❌ | 1 | 100.0 | 47 | 47 | 47 | 1.0 | - |
| Validation: missing symbol | ❌ | 1 | 100.0 | 61 | 61 | 61 | 1.0 | - |
| Validation: negative qty | ❌ | 1 | 100.0 | 61 | 61 | 61 | 1.0 | - |
| Validation: string qty | ❌ | 1 | 100.0 | 42 | 42 | 42 | 1.0 | - |
| Validation: unknown order type | ❌ | 1 | 100.0 | 45 | 45 | 45 | 1.0 | - |
| Validation: zero qty | ❌ | 1 | 100.0 | 89 | 89 | 89 | 1.0 | - |
| Load: ORDER close position | ✅ | 10 | 0.0 | 140 | 191 | 191 | 3.25 | 5000 |
| Load: ORDER place market | ✅ | 10 | 0.0 | 201 | 251 | 251 | 3.19 | 5000 |
| Load: READ orders (history) | ✅ | 4 | 0.0 | 278 | 293 | 293 | 1.99 | 6000 |
| Load: READ positions | ✅ | 438 | 0.0 | 100 | 125 | 145 | 29.71 | 2500 |
| Integrity: no orphan positions / stuck margin after load | ❌ | - | - | - | - | - | - | - |

## Findings

- **Validation: absurd tp/sl** - KNOWN PLATFORM BUG - absurd TP/SL (tp=-1, sl=1e30) is accepted. got 200 Test failed: code expected to equal /

****** received  : [[[2]]]00

****** comparison: [[[4]]]00

/
- **Validation: bad side** - got 400 
- **Validation: missing symbol** - got 400 
- **Validation: negative qty** - got 400 
- **Validation: string qty** - got 400 
- **Validation: unknown order type** - KNOWN PLATFORM BUG - unknown order type returns 500 instead of 400. got 500 Test failed: code expected to equal /

****** received  : [[[5]]]00

****** comparison: [[[4]]]00

/
- **Validation: zero qty** - got 400 
- **Integrity: no orphan positions / stuck margin after load** - 21 accounts still hold 21 positions after the master closed everything; 21 with stuck margin; e.g. {'follower3@mailinator.com': 1, 'follower1@mailinator.com': 1, 'ctmaster@mailinator.com': 1}
