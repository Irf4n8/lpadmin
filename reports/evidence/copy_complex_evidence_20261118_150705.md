# Complex Copy-Trading Scenarios

**Generated:** 2026-11-18T09:37:05.398423+00:00  
**Instance:** `real` | **Followers:** 10 | **Seed:** 1234

| Scenario | Result | Findings |
| :--- | :---: | :--- |
| X1 Mixed-mode sizing | ✅ PASS | 0 HIGH, 0 MED |
| X2 Reverse lifecycle | ⚠️ WARN | 0 HIGH, 1 MED |
| X3 Pyramid + partial cascade | ✅ PASS | 0 HIGH, 0 MED |
| X4 Protection sync | ✅ PASS | 0 HIGH, 0 MED |
| X5 Follower intervention | ✅ PASS | 0 HIGH, 0 MED |
| X6 Multiplier change mid-trade | ✅ PASS | 0 HIGH, 0 MED |
| X7 Phantom-copy check | ✅ PASS | 0 HIGH, 0 MED |
| X8 Open/close churn | ✅ PASS | 0 HIGH, 0 MED |
| X9 Chained concurrent ops | ✅ PASS | 0 HIGH, 0 MED |
| X10 Seeded random walk (seed 1234) | ✅ PASS | 0 HIGH, 0 MED |

## Findings

### X2 Reverse lifecycle
- **MED** - reverse follower PnL (-3.100) has the SAME sign as master (-3.000)
- **INFO** - PnL master -3.000 | normal follower -3.000 | reverse follower -3.100

### X6 Multiplier change mid-trade
- **INFO** - after closing master's first position follower net is 1.5 (second position still open on master)

### X8 Open/close churn
- **INFO** - churn PnL master -36.10 | normal followers avg -36.10 (min -36.10, max -36.10)

