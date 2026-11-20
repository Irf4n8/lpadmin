"""Bounded staging follow-up; execute only on the explicitly authorized staging host."""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import settings as s
from test_suite.client import BlackTraderClient
from test_suite import breakpoint_race_runner as r


def main():
    c = BlackTraderClient(timeout=15)
    emails = [f'{s.DEFAULT_PREFIX}{i}@{s.DEFAULT_DOMAIN}' for i in range(1, 7)]
    evidence = {'timestamp': datetime.now(timezone.utc).isoformat(), 'host': s.BASE_URL,
                'instance': 'real', 'results': [], 'order_responses': []}
    place = c.place_order
    balance = c.set_member_balance
    def small_order(email, *args, **kwargs):
        if kwargs.get('qty', 0) == 1.0:
            kwargs['qty'] = 0.01
        result = place(email, *args, **kwargs)
        evidence['order_responses'].append({'email': email, 'qty': kwargs.get('qty'), 'response': result})
        return result
    c.place_order = small_order
    try:
        for fn in (r.b1_dup_squareoff, r.b2_over_reduce):
            evidence['results'].append(fn(c, s.MASTER_EMAIL, emails, 'real'))
        # A low follower balance exercises margin rejection while the master can
        # still afford the bounded burst. Restore the exact original via runner finally.
        first_balance_write = True
        def low_balance(mid, value, instance='real', **kwargs):
            nonlocal first_balance_write
            target = 10.0 if first_balance_write else value
            first_balance_write = False
            return balance(mid, target, instance, **kwargs)
        c.set_member_balance = low_balance
        result = r.b7_margin_exhaustion(c, s.MASTER_EMAIL, emails, 'real')
        result['metrics']['test_follower_balance'] = 10.0
        result['metrics']['test_master_order_qty'] = 0.01
        if result['metrics'].get('master_orders', 0) == 0:
            result['status'] = 'BLOCKED'
        evidence['results'].append(result)
    finally:
        r.reset(c, s.MASTER_EMAIL, emails, 'real')
        evidence['results'].append(r.b11_audit(c, s.MASTER_EMAIL, emails, 'real'))
        path = Path(__file__).resolve().parents[1] / 'reports/evidence/staging_race_followup.json'
        path.write_text(json.dumps(evidence, indent=2, default=str))
        print('Evidence:', path)
    return 1 if any(x['status'] in ('FAIL', 'ERROR', 'BLOCKED') for x in evidence['results']) else 0


if __name__ == '__main__':
    raise SystemExit(main())
