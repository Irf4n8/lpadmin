# Breakpoint & Race-Condition Hunter Report

**Generated:** 2026-11-12T09:48:07.153472+00:00  
**Instance:** `paper` | **Followers:** 10 | **Master:** `ctmaster@mailinator.com`

| Scenario | Result | Findings |
| :--- | :---: | :--- |
| B1 Duplicate squareoff storm | ✅ PASS | 0 HIGH, 0 MED |
| B2 Over-reduce race | ✅ PASS | 0 HIGH, 0 MED |
| B3 Protection write storm | ⏭️ SKIP | 0 HIGH, 1 MED |
| B4 Double-cancel storm | ⏭️ SKIP | 0 HIGH, 1 MED |
| B5 Load ramp (breaking point) | ✅ PASS | 0 HIGH, 0 MED |
| B6 Follow/unfollow flapping | ✅ PASS | 0 HIGH, 0 MED |
| B7 Margin exhaustion | ✅ PASS | 0 HIGH, 0 MED |
| B8 | 💥 ERROR | 1 HIGH, 0 MED |
| B9 Bulk vs individual close | ✅ PASS | 0 HIGH, 0 MED |
| B10 Auth/token refresh storm | ✅ PASS | 0 HIGH, 0 MED |
| B11 Final consistency audit | ✅ PASS | 0 HIGH, 0 MED |

## Findings

### B3 Protection write storm
- **MED** — could not read entry price; skipping

### B4 Double-cancel storm
- **MED** — no market price available; skipping

### B5 Load ramp (breaking point)
- **INFO** — first degradation at: not reached concurrent master orders

### B8
- **HIGH** — runner exception: 'payload'

## Load ramp

| Threads | Placed | p50 s | p95 s | Fan-out lag s | Short | Dup | Positions |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| 10 | 10 | 0.601 | 0.843 | 0.39 | 0 | 0 | 100/100 |
| 25 | 25 | 1.68 | 2.446 | 0.4 | 0 | 0 | 250/250 |
