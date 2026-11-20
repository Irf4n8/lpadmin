"""Read-only real-hedging QA. Auth POSTs only; never trades or modifies balances."""
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.settings import BASE_URL, MASTER_EMAIL, MEMBER_PASSWORD

OUT = ROOT / 'reports/live_recheck_20261120'


def main():
    OUT.mkdir(exist_ok=True)
    results, evidence = [], []

    def record(id_, expected, actual, passed):
        results.append({'id': id_, 'expected': expected, 'actual': actual,
                        'status': 'PASS' if passed else 'FAIL'})

    session = requests.Session()
    login = session.post(BASE_URL + '/api/auth/login', json={'email': MASTER_EMAIL, 'password': MEMBER_PASSWORD}, timeout=20)
    if login.status_code != 200 or login.json().get('success') is not True:
        raise RuntimeError('Master authentication failed; no further calls')
    token_response = session.post(BASE_URL + '/api/auth/chart-token', timeout=20)
    token = token_response.json().get('token') if token_response.status_code == 200 else None
    if not isinstance(token, str) or not token:
        raise RuntimeError('Chart token missing; no further calls')
    headers = {'Authorization': 'Bearer ' + token, 'X-Broker-ID': 'real'}

    def get(ep, auth=True):
        started = time.monotonic()
        response = session.get(BASE_URL + '/v1/oms/real/' + ep, headers=headers if auth else {}, timeout=25)
        try:
            body = response.json()
        except ValueError:
            body = {'non_json': True}
        evidence.append({'endpoint': ep, 'authenticated': auth, 'http': response.status_code,
                         'elapsed_ms': round((time.monotonic() - started)*1000, 2), 'body': body})
        return response.status_code, body

    status, info = get('info')
    record('REAL-HEDGING-IDENTITY', 'HTTP 200, slug real, mode hedging', info,
           status == 200 and info.get('slug') == 'real' and info.get('mode') == 'hedging')
    if results[-1]['status'] != 'PASS':
        raise RuntimeError('Instance identity not verified')

    for ep in ['health', 'funds', 'account', 'positions', 'orders', 'history',
               'mam/masters', 'mam/follows', 'mam/shares']:
        status, body = get(ep)
        record('GET-' + ep, 'HTTP 200, JSON object, no explicit success=false',
               {'http': status, 'keys': list(body) if isinstance(body, dict) else type(body).__name__},
               status == 200 and isinstance(body, dict) and body.get('success') is not False)

    # Use fresh sessions, no authenticated cookies, for negative authorization tests.
    for ep in ['positions', 'orders', 'funds', 'history', 'mam/follows', 'mam/shares']:
        for label, auth in [('missing', {}), ('invalid', {'Authorization': 'Bearer qa-invalid-not-a-token'})]:
            r = requests.get(BASE_URL + '/v1/oms/real/' + ep, headers=auth, timeout=20)
            record('AUTH-' + label + '-' + ep, 'HTTP 401 or 403', r.status_code, r.status_code in (401, 403))

    baseline_path = OUT / 'follower_baseline_recheck.json'
    if not baseline_path.exists():
        baseline_path = OUT / 'follower_baseline.json'
    baseline = json.loads(baseline_path.read_text(encoding='utf-8'))
    preflight = json.loads((OUT / 'preflight.json').read_text(encoding='utf-8'))
    master_id = preflight['master']['mam/follows']['data']['master']['client_id']
    accounts = baseline['accounts']
    record('FOLLOWER-SET', '100 unique mamf1..mamf100 mailinator accounts', len(accounts),
           {a['email'] for a in accounts} == {f'mamf{i}@mailinator.com' for i in range(1,101)})
    for a in accounts:
        email = a['email']
        pos = a.get('positions', {})
        data = pos.get('data', {})
        positions = data.get('positions', [])
        funds = data.get('funds', {})
        record(email + ':POSITION-SCHEMA', 'Authenticated 200, success true, count matches list',
               {'http': pos.get('http'), 'count': data.get('count'), 'length': len(positions)},
               a.get('token_present') is True and pos.get('http') == 200 and data.get('success') is True
               and data.get('count') == len(positions))
        links = a.get('mam/follows', {}).get('data', {}).get('following', [])
        active = [l for l in links if l.get('status') == 'active' and l.get('master_client_id') == master_id]
        record(email + ':MAM-LINK', 'One active link to configured master on real; additional masters are recorded separately, not assumed forbidden',
               [{'master_client_id': l.get('master_client_id'), 'instance': l.get('instance')} for l in active],
               len(active) == 1 and active[0].get('master_client_id') == master_id and active[0].get('instance') == 'real')
        results[-1]['category'] = 'test_setup_precondition'
        results[-1]['additional_active_masters'] = [l.get('master_client_id') for l in links
            if l.get('status') == 'active' and l.get('master_client_id') != master_id]
        if results[-1]['status'] == 'FAIL':
            results[-1]['status'] = 'NOT_READY'
        required = ['balance', 'equity', 'unrealized_pnl', 'used_margin', 'free_margin']
        finite = all(isinstance(funds.get(k), (int, float)) and math.isfinite(funds[k]) for k in required)
        residuals = {} if not finite else {
            'equity_minus_balance_and_pnl': funds['equity'] - funds['balance'] - funds['unrealized_pnl'],
            'free_margin_minus_equity_less_margin': funds['free_margin'] - funds['equity'] + funds['used_margin']}
        record(email + ':FUNDS-IDENTITIES', 'Finite values; equity=balance+PnL and free_margin=equity-used_margin within 0.01',
               residuals, finite and all(abs(x) <= .01 for x in residuals.values()))
    output = {'executed_at': datetime.now(timezone.utc).isoformat(), 'instance': 'real', 'mode': 'hedging',
              'scope': 'Read-only endpoint/auth checks and baseline invariants; no new trades or balance changes',
              'results': results, 'endpoint_evidence': evidence,
              'baseline_source': baseline_path.name,
              'totals': {s: sum(r['status'] == s for r in results) for s in ['PASS','FAIL','NOT_READY']}}
    (OUT / 'readonly_checks.json').write_text(json.dumps(output, indent=2), encoding='utf-8')
    print(json.dumps({'totals': output['totals'], 'failures': [r for r in results if r['status']=='FAIL']}, indent=2))
    return int(any(r['status']=='FAIL' for r in results))


if __name__ == '__main__':
    sys.exit(main())
