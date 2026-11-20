"""Capture sequential vs concurrent close accounting on the authorized staging account."""
import json
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import settings as s
from test_suite.client import BlackTraderClient
from test_suite import breakpoint_race_runner as r

c = BlackTraderClient()
email = f'{s.DEFAULT_PREFIX}1@{s.DEFAULT_DOMAIN}'
evidence = {}
try:
    for name, n in [('sequential', 1), ('concurrent', 20)]:
        assert c.get_positions(email, 'real')['count'] == 0
        order = c.place_order(email, qty=0.01, instance='real')
        mid = r.mkt_id(order)
        assert mid, order
        before = c.get_positions(email, 'real')
        responses = r.parallel(lambda _: c.squareoff_position(email, mid, 'real'), n)
        time.sleep(1)
        after = c.get_positions(email, 'real')
        evidence[name] = {'order': order, 'before': before, 'responses': responses, 'after': after,
                          'balance_delta': after['funds']['balance'] - before['funds']['balance']}
    links = c.get_copy_followers(s.MASTER_EMAIL, 'real', active_only=False)
    evidence['probe_links'] = [x for x in links if x.get('follower_name') == f'{s.DEFAULT_PREFIX}6']
finally:
    c.bulk_squareoff(email, 'real')
    c.bulk_cancel(email, 'real')
    path = Path(__file__).resolve().parents[1] / 'reports/evidence/staging_close_control.json'
    path.write_text(json.dumps(evidence, indent=2))
    for name in ('sequential', 'concurrent'):
        if name in evidence:
            x = evidence[name]
            print(name, json.dumps({'balance_delta': x['balance_delta'], 'responses': x['responses'],
                                   'remaining': x['after']['count']}))
    print('Probe links:', json.dumps(evidence.get('probe_links')))
    print('Evidence:', path)
