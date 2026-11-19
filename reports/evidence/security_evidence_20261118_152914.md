# Security Test Report

**Generated:** 2026-11-18T09:59:14.038970+00:00  
**Target:** `https://lpadmin.blackfx.com` (paper, test accounts)

| Check | Result | HIGH | MED |
| :--- | :---: | ---: | ---: |
| S1 Unauthenticated access | ✅ PASS | 0 | 0 |
| S2 Invalid and tampered tokens | ✅ PASS | 0 | 0 |
| S3 IDOR (cross-account access) | ❌ FAIL | 1 | 0 |
| S4 Vertical privilege (trader -> admin) | ✅ PASS | 0 | 0 |
| S5 Copy-trading data exposure | ✅ PASS | 0 | 0 |
| S6 Login hardening | ✅ PASS | 0 | 0 |
| S7 Injection | ✅ PASS | 0 | 0 |
| S8 Malformed and oversized requests | ✅ PASS | 0 | 0 |
| S9 Transport and headers | ⚠️ WARN | 0 | 5 |
| S10 Error hygiene | ✅ PASS | 0 | 0 |

## Findings

### S3 IDOR (cross-account access)
- **HIGH** - victim's position disappeared after cross-account attempts

### S6 Login hardening
- **INFO** - session cookie lives 399 days (long-lived; consider shorter for a trading platform)

### S9 Transport and headers
- **MED** - plain http:// returns 200 and is not redirected to https:// (HSTS only protects after the first visit)
- **MED** - CORS allows origin 'https://evil.example' (ACAO=*, credentials=None)
- **MED** - CORS allows origin 'null' (ACAO=*, credentials=None)
- **MED** - server still accepts TLS 1.0
- **MED** - server still accepts TLS 1.1

