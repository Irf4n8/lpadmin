"""Offline QA probes. No remote requests or application-code changes.
Run: python reports/qa_retest_20261120.py
FAIL means the application's observed behavior violates the stated expectation.
"""
import ast
import contextlib
import io
import json
import math
import runpy
import socket
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
RESULTS = []


def check(name, expected, actual, ok):
    RESULTS.append(dict(name=name, expected=expected, actual=actual, status="PASS" if ok else "FAIL"))


def run():
    from test_suite.client import BlackTraderClient
    from test_suite.scenarios import ScenarioRunner, compute_latencies
    from run_all_165_mam_tests import MamMasterTestExecutor
    from run_basic_10_test_cases import BlackTraderUserSession
    from dashboard.suites import SUITES, build_command, needs_confirmation
    from reusable.helpers import calculate_order_prices
    from dashboard import testops

    files = list(ROOT.rglob('*.py'))
    errors = []
    for p in files:
        try:
            ast.parse(p.read_text(encoding='utf-8-sig'), filename=str(p))
        except Exception as e:
            errors.append({'file': str(p.relative_to(ROOT)), 'error': str(e)})
    check('Python syntax', 'All Python files parse', {'files': len(files), 'errors': errors}, not errors)

    scenarios = json.loads((ROOT / 'scratch/all_165_scenarios.json').read_text(encoding='utf-8'))
    ex = MamMasterTestExecutor()
    ex.client = Mock()
    response = Mock(status_code=503, text='simulated unavailable')
    response.json.return_value = {'success': False}
    ex.client.request_with_retry.return_value = response
    sc = next(s for s in scenarios if s['id'] == 'MAM-F003')
    result = ex.execute_scenario(sc)
    check('F003 API failure handling', 'Must not PASS when both endpoints return 503',
          {'status': result['status'], 'evidence': result['evidence']}, result['status'] != 'PASS')
    ex.client.reset_mock()
    sc = next(s for s in scenarios if s['id'] == 'MAM-A001')
    result = ex.execute_scenario(sc)
    check('Calculation-only production certification', 'No production-ready claim without platform verification',
          {'assessment': result['go_live_assessment'], 'client_calls': len(ex.client.mock_calls)},
          result['go_live_assessment'] != 'PASSED_PRODUCTION_READY')

    client = BlackTraderClient()
    client.get_trader_token = Mock(return_value='offline-token')
    client.request_with_retry = Mock(return_value=response)
    for method in ('bulk_squareoff', 'bulk_cancel'):
        result = getattr(client, method)('offline@example.invalid')
        check(method + ' on read failure', 'Must not return success when inventory read fails', result,
              result['status_code'] != 200)

    fake = Mock()
    fake.squareoff_position.return_value = {'status_code': 503}
    fake.fetch_all_followers_positions.return_value = {'f': {'count': 0, 'positions': [], 'error': 'HTTP 503'}}
    runner = ScenarioRunner(fake, 'm', ['f'])
    with patch('test_suite.scenarios.time.sleep'), contextlib.redirect_stdout(io.StringIO()):
        result = runner.test_full_close(['order-1'])
    check('Full close with failed close and failed verification', 'FAIL or BLOCKED', result, result['status'] != 'PASS')

    user = BlackTraderUserSession('offline@example.invalid', 'offline', 'offline')
    user.session = Mock()
    login = Mock(status_code=200)
    login.json.return_value = {'success': True}
    token = Mock(status_code=200)
    token.json.return_value = {}
    user.session.post.side_effect = [login, token]
    authenticated = user.authenticate()
    check('Authentication missing chart token', False, authenticated, authenticated is False)

    client = BlackTraderClient()
    client.session = Mock()
    client.session.request.side_effect = [__import__('requests').Timeout('response lost after commit'), Mock(status_code=200)]
    with patch('test_suite.client.time.sleep'):
        client.request_with_retry('POST', 'https://offline.invalid/orders', json={'qty': 1})
    count = client.session.request.call_count
    check('Order POST retry after ambiguous timeout', 'No automatic replay without an idempotency guarantee',
          {'attempts': count, 'idempotency_header': False}, count == 1)

    suite = next(s for s in SUITES if 'lot' in s['flags'])
    cmd = build_command(suite, {'lot': 'inf'}, {'follower_count': 2})
    lot = cmd[cmd.index('--lot') + 1]
    check('Reject nonfinite lot', 'Finite positive lot or validation error', lot, math.isfinite(float(lot)))
    check('Real instance confirmation guard', True, needs_confirmation(suite, {'instance': 'real'}),
          needs_confirmation(suite, {'instance': 'real'}))
    cmd = build_command(suite, {'start': 5, 'end': 2}, {'follower_count': 2})
    check('Follower range normalization', ['2', '5'], [cmd[cmd.index('--start')+1], cmd[cmd.index('--end')+1]],
          cmd[cmd.index('--start')+1] == '2' and cmd[cmd.index('--end')+1] == '5')
    for kind in ['MARKET', 'LIMIT', 'STOP']:
        for side in ['BUY', 'SELL']:
            prices = calculate_order_prices(kind, side, 60000, 1, 50, 100, 100)
            base = prices['base_price']
            ok = prices['tp_price'] > base > prices['sl_price'] if side == 'BUY' else prices['tp_price'] < base < prices['sl_price']
            if kind != 'MARKET':
                ok = ok and base == prices['trigger_price']
            check(kind + ' ' + side + ' protection reference', 'Correct side and entry reference', prices, ok)
    lat = compute_latencies('2026-11-20T00:00:00Z', ['2026-11-20T00:00:00.100Z'])
    check('ISO Z latency calculation', 100.0, lat['avg_ms'], lat['avg_ms'] == 100.0)

    for entry in ['main.py'] + [s['script'] for s in SUITES if s.get('script')]:
        try:
            with patch.object(sys, 'argv', [entry, '--help']), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                runpy.run_path(str(ROOT / entry), run_name='__main__')
            outcome = 0
        except SystemExit as e:
            outcome = e.code
        except Exception as e:
            outcome = type(e).__name__ + ': ' + str(e)
        check('CLI help: ' + entry, 0, outcome, outcome == 0)
    try:
        with patch.object(sys, 'argv', ['runner.py', '--start', '2', '--end', '1']), contextlib.redirect_stdout(io.StringIO()):
            runpy.run_path(str(ROOT / 'test_suite/runner.py'), run_name='__main__')
        outcome = 'accepted'
    except SystemExit as e:
        outcome = 'validation exit ' + str(e.code)
    except Exception as e:
        outcome = type(e).__name__ + ': ' + str(e)
    check('CLI reversed follower range', 'Validation error or normalized range', outcome,
          outcome.startswith('validation exit'))
    for name, payload, expected_code in [('unknown suite', {'suite': 'does-not-exist'}, 400),
            ('unconfirmed real execution', {'suite': suite['key'], 'params': {'instance': 'real'}}, 412)]:
        with patch('dashboard.testops.subprocess.Popen', side_effect=AssertionError('Must not launch')):
            _, code = testops.run_suite(payload)
        check('Testops rejects ' + name, expected_code, code, code == expected_code)
    try:
        with patch('dashboard.testops.subprocess.Popen', side_effect=AssertionError('Must not launch')):
            _, outcome = testops.run_suite({'suite': suite['key'], 'params': ['invalid']})
    except Exception as e:
        outcome = type(e).__name__ + ': ' + str(e)
    check('Testops malformed params', 400, outcome, outcome == 400)

    tree = ast.parse((ROOT / 'run_all_165_mam_tests.py').read_text(encoding='utf-8'))
    unconditional = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                     and n.func.attr == 'format_result' and any(k.arg == 'status' and isinstance(k.value, ast.Constant)
                     and k.value.value == 'PASS' for k in n.keywords)]
    archive = ROOT / 'reports/live_recheck_20261120/historical_reports_before_rewrite.zip'
    if archive.exists():
        import zipfile
        with zipfile.ZipFile(archive) as z:
            old = json.loads(z.read('mam_test_execution_reports/MAM_MASTER_SUMMARY.json'))
    else:
        old = json.loads((ROOT / 'mam_test_execution_reports/MAM_MASTER_SUMMARY.json').read_text(encoding='utf-8'))
    output = {'executed_at': datetime.now(timezone.utc).isoformat(), 'mode': 'offline; outbound sockets blocked',
              'results': RESULTS, 'totals': dict(Counter(r['status'] for r in RESULTS)),
              'historical_report_not_retested': {'total': old['total_scenarios'], 'claimed_passed': old['passed_scenarios'],
                  'verification_types': dict(Counter(r['verification_type'] for r in old['results']))},
              'unconditional_pass_call_sites': unconditional}
    dest = ROOT / 'reports/qa_retest_20261120.json'
    dest.write_text(json.dumps(output, indent=2), encoding='utf-8')
    print(json.dumps(output, indent=2))
    return 1 if any(r['status'] == 'FAIL' for r in RESULTS) else 0


if __name__ == '__main__':
    with patch.object(socket.socket, 'connect', side_effect=RuntimeError('QA blocks outbound network')):
        sys.exit(run())
