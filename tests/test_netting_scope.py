"""The financial runner must reject out-of-scope inputs before account/network setup."""
import sys

import pytest

from test_suite import fresh_netting_staging_runner as runner


@pytest.mark.parametrize('extra',[
    ['--only','MAM'],['--only','PAMM'],['--only','ALGO'],
    ['--books','unknown'],['--books','real-net'],
    ['--repeat','0'],['--repeat','11'],
])
def test_scope_rejected_before_account_or_network_setup(monkeypatch,extra):
    initialized=[]
    def forbidden_setup(*args,**kwargs):
        initialized.append(True)
        raise AssertionError('Invalid scope reached account setup')
    monkeypatch.setattr(runner,'NettingRun',forbidden_setup)
    monkeypatch.setattr(runner.cfg,'BASE_URL','https://lpadmin.blackfx.com')
    monkeypatch.setattr(sys,'argv',['runner','--confirm-staging','--accounts','unused.json']+extra)
    with pytest.raises(SystemExit) as exc:
        runner.main()
    assert exc.value.code==2
    assert not initialized
