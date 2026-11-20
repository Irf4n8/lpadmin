# Breakpoint & Race-Condition Hunter Report

**Generated:** 2026-11-20T04:34:53.892343+00:00  
**Instance:** `real` | **Followers:** 6 | **Master:** `master2@mailinator.com`

| Scenario | Result | Findings |
| :--- | :---: | :--- |
| B1 Duplicate squareoff storm | ❌ FAIL | 1 HIGH, 0 MED |
| B2 Over-reduce race | ❌ FAIL | 1 HIGH, 0 MED |
| B3 Protection write storm | ✅ PASS | 0 HIGH, 0 MED |
| B4 Double-cancel storm | ✅ PASS | 0 HIGH, 0 MED |
| B5 Load ramp (breaking point) | ⚠️ WARN | 0 HIGH, 1 MED |
| B6 Follow/unfollow flapping | ✅ PASS | 0 HIGH, 0 MED |
| B7 Margin exhaustion | ✅ PASS | 0 HIGH, 0 MED |
| B8 Input fuzz | ✅ PASS | 0 HIGH, 0 MED |
| B9 Bulk vs individual close | ✅ PASS | 0 HIGH, 0 MED |
| B10 Auth/token refresh storm | ✅ PASS | 0 HIGH, 0 MED |
| B11 Final consistency audit | ✅ PASS | 0 HIGH, 0 MED |

## Findings

### B1 Duplicate squareoff storm
- **HIGH** — follower did not receive copied position - cannot run scenario

### B2 Over-reduce race
- **HIGH** — no follower position

### B5 Load ramp (breaking point)
- **MED** — @20 concurrent: non-200 responses {400: 8}
- **INFO** — first degradation at: 20 concurrent master orders

## Load ramp

| Threads | Placed | p50 s | p95 s | Fan-out lag s | Short | Dup | Positions |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| 5 | 5 | 0.204 | 0.234 | 0.06 | 0 | 0 | 30/30 |
| 10 | 10 | 0.182 | 0.259 | 0.09 | 0 | 0 | 60/60 |
| 20 | 12 | 0.284 | 0.323 | 0.08 | 0 | 0 | 72/72 |
