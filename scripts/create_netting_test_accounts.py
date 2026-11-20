"""Provision three fresh accounts explicitly requested for staging netting tests."""
from datetime import datetime,timezone
import argparse
import json
from pathlib import Path
import sys
import requests

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import settings as cfg
from test_suite.client import BlackTraderClient


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--resume',action='store_true')
    args=parser.parse_args()
    if cfg.BASE_URL!='https://lpadmin.blackfx.com' or not cfg.MEMBER_PASSWORD:
        raise RuntimeError('Requires the authorized staging host and configured test password')
    client=BlackTraderClient(timeout=12)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    path=ROOT/'reports/evidence'/('netting_fresh_accounts_'+stamp+'.json')
    result=dict(created_at=datetime.now(timezone.utc).isoformat(),host=cfg.BASE_URL,
                purpose='Fresh user-authorized staging netting master/follower fixtures',accounts=[])
    if args.resume:
        result=json.loads((ROOT/'reports/netting_fresh_accounts.json').read_text())
        stamp=result['accounts'][0]['email'].split('.')[1]
        path=ROOT/'reports/evidence'/('netting_fresh_accounts_'+stamp+'.json')
    headers={'Authorization':'Bearer '+client.get_admin_token()}
    try:
        for role in ('master','follower1','follower2'):
            if any(r['intended_role']==role for r in result['accounts']):continue
            email=f'netqa.{stamp}.{role}@mailinator.com'
            response=requests.post(cfg.BASE_URL+'/admin/api/members',headers=headers,
                                   json={'email':email,'password':cfg.MEMBER_PASSWORD,'name':{'master':'Netting QA Master','follower1':'Netting QA Alpha','follower2':'Netting QA Bravo'}[role]},timeout=15)
            data=response.json()
            if response.status_code not in (200,201):
                raise RuntimeError(f'Create {role}: HTTP{response.status_code}; {str(data)[:250]}')
            member=data.get('member',{})
            allowed=('email','member_id','account_type','book','status','plan','group_code','balances')
            row={k:member.get(k) for k in allowed}
            row.update(email=email,intended_role=role,create_http=response.status_code)
            result['accounts'].append(row)
            path.write_text(json.dumps(result,indent=2))
            print('CREATED',role,email,row.get('member_id'),flush=True)
    finally:
        path.write_text(json.dumps(result,indent=2))
        (ROOT/'reports/netting_fresh_accounts.json').write_text(json.dumps(result,indent=2))
        print('MANIFEST',path,flush=True)


if __name__=='__main__':main()
