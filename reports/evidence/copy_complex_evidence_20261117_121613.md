# Complex Copy-Trading Scenarios

**Generated:** 2026-11-17T06:46:13.547444+00:00  
**Instance:** `real` | **Followers:** 20 | **Seed:** 1234

| Scenario | Result | Findings |
| :--- | :---: | :--- |
| X1 Mixed-mode sizing | ✅ PASS | 0 HIGH, 0 MED |
| X2 Reverse lifecycle | ✅ PASS | 0 HIGH, 0 MED |
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
- **INFO** - PnL master -0.100 | normal follower -0.100 | reverse follower +0.000

### X6 Multiplier change mid-trade
- **INFO** - after closing master's first position follower net is 1.5 (second position still open on master)

### X8 Open/close churn
- **INFO** - churn PnL master -0.20 | normal followers avg +1.02 (min +1.02, max +1.03)

