# Browser User-Journey Report

**Generated:** 2026-11-12T12:23:56.519435+00:00  
**Target:** `https://lpadmin.blackfx.com`  
**Screenshots:** `reports/evidence/screenshots/journey_*.png`

| Journey | Result | HIGH | MED |
| :--- | :---: | ---: | ---: |
| U1-U3 Auth gate, wrong password, login | ✅ PASS | 0 | 0 |
| U4-U6 Terminal loads, tabs, trades panel | ❌ FAIL | 3 | 0 |
| U7 Logout gates the app again | ✅ PASS | 0 | 0 |
| U8 Admin panel journey | ✅ PASS | 0 | 0 |
| U9 Mobile viewport | ✅ PASS | 0 | 0 |
| U10 Client-side hygiene (whole journey) | ⚠️ WARN | 0 | 1 |

## Findings

### U4-U6 Terminal loads, tabs, trades panel
- **HIGH** - U6 Trades tab 'Orders' could not be opened: TimeoutError
- **HIGH** - U6 Trades tab 'History' could not be opened: TimeoutError
- **HIGH** - U6 Trades tab 'Funds' could not be opened: TimeoutError

### U10 Client-side hygiene (whole journey)
- **INFO** - client error 401 while browsing: https://lpadmin.blackfx.com/api/auth/login
- **MED** - the Content-Security-Policy blocks Cloudflare's analytics beacon (cloudflareinsights) - 19 console errors on every page load; allow it in script-src or remove the Cloudflare Web Analytics snippet


## Metrics

```json
{
 "U1-U3 Auth gate, wrong password, login": {
  "login_to_account_s": 1.0
 },
 "U4-U6 Terminal loads, tabs, trades panel": {
  "terminal_ready_s": 3.3,
  "trades_positions_s": 0.1,
  "trades_pending_s": 0.2
 },
 "U8 Admin panel journey": {
  "admin_members_visible_samples": 1
 },
 "U10 Client-side hygiene (whole journey)": {
  "js_errors": 0,
  "http_5xx": 0,
  "http_4xx": 1,
  "slow": 0
 }
}
```
