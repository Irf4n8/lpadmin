# Browser User-Journey Report

**Generated:** 2026-11-12T12:22:09.018149+00:00  
**Target:** `https://lpadmin.blackfx.com`  
**Screenshots:** `reports/evidence/screenshots/journey_*.png`

| Journey | Result | HIGH | MED |
| :--- | :---: | ---: | ---: |
| U1-U3 Auth gate, wrong password, login | ✅ PASS | 0 | 0 |
| U4-U6 Terminal loads, tabs, trades panel | ❌ FAIL | 2 | 0 |
| U7 Logout gates the app again | ✅ PASS | 0 | 0 |
| U8 Admin panel journey | ✅ PASS | 0 | 0 |
| U9 Mobile viewport | ✅ PASS | 0 | 0 |
| U10 Client-side hygiene (whole journey) | ⚠️ WARN | 0 | 2 |

## Findings

### U4-U6 Terminal loads, tabs, trades panel
- **HIGH** - U6 Trades tab 'Orders' could not be opened: TimeoutError
- **HIGH** - U6 Trades tab 'History' could not be opened: TimeoutError
- **INFO** - U6 'Orders' tab lists 4624 entries for one account (history is never trimmed/paginated)

### U10 Client-side hygiene (whole journey)
- **MED** - JS/console error: Failed to load resource: the server responded with a status of 401 ()
- **INFO** - client error 401 while browsing: https://lpadmin.blackfx.com/api/auth/login
- **MED** - the Content-Security-Policy blocks Cloudflare's analytics beacon (cloudflareinsights) - 19 console errors on every page load; allow it in script-src or remove the Cloudflare Web Analytics snippet


## Metrics

```json
{
 "U1-U3 Auth gate, wrong password, login": {
  "login_to_account_s": 1.0
 },
 "U4-U6 Terminal loads, tabs, trades panel": {
  "terminal_ready_s": 3.1,
  "trades_positions_s": 0.1,
  "trades_pending_s": 0.1,
  "trades_funds_s": 0.2,
  "orders_count_in_tab": 4624
 },
 "U8 Admin panel journey": {
  "admin_members_visible_samples": 1
 },
 "U10 Client-side hygiene (whole journey)": {
  "js_errors": 1,
  "http_5xx": 0,
  "http_4xx": 1,
  "slow": 0
 }
}
```
