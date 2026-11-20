"""Deterministic concurrency checks. No network requests or live account changes."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
from types import SimpleNamespace

import pytest

from test_suite.client import BlackTraderClient


def together(n, fn):
    gate = Barrier(n)
    def run(i):
        gate.wait(timeout=5)
        return fn(i)
    with ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(run, range(n)))


@pytest.mark.parametrize("workers", [2, 8, 32])
def test_admin_cache_misses_share_login(monkeypatch, workers):
    client = BlackTraderClient()
    calls = []
    def request(*args, **kwargs):
        calls.append(1)
        return SimpleNamespace(status_code=200, json=lambda: {"token": "admin-test"})
    monkeypatch.setattr(client, "request_with_retry", request)
    assert together(workers, lambda _: client.get_admin_token()) == ["admin-test"] * workers
    assert len(calls) == 1


def test_different_traders_authenticate_concurrently_without_cookie_leaks(monkeypatch):
    from test_suite import client as module
    client = BlackTraderClient()
    gate = Barrier(8)
    closed = []
    class Session:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            closed.append(self.email)
        def post(self, url, **kwargs):
            if url.endswith('/login'):
                self.email = kwargs['json']['email']
                gate.wait(timeout=5)
            return SimpleNamespace(status_code=200, json=lambda: {"token": self.email})
    monkeypatch.setattr(module.requests, 'Session', Session)
    emails = [f'local{i}@example.test' for i in range(8)]
    assert together(8, lambda i: client.get_trader_token(emails[i])) == emails
    assert sorted(closed) == sorted(emails)
    assert client._tokens == dict(zip(emails, emails))


def test_trader_login_failure_releases_lock_for_waiting_call(monkeypatch):
    from test_suite import client as module
    client = BlackTraderClient()
    lock = Lock()
    attempts = []
    closed = []
    class Session:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            closed.append(1)
        def post(self, url, **kwargs):
            if url.endswith('/login'):
                with lock:
                    attempts.append(1)
                    code = 503 if len(attempts) == 1 else 200
                return SimpleNamespace(status_code=code, text='test failure')
            return SimpleNamespace(status_code=200, json=lambda: {'token': 'recovered'})
    monkeypatch.setattr(module.requests, 'Session', Session)
    def authenticate(_):
        try:
            return client.get_trader_token('local@example.test')
        except RuntimeError:
            return 'failed'
    results = together(8, authenticate)
    assert results.count('failed') == 1
    assert results.count('recovered') == 7
    assert len(attempts) == len(closed) == 2


@pytest.mark.parametrize('workers', [8, 32])
def test_concurrent_history_adds_do_not_lose_entries(monkeypatch, tmp_path, workers):
    from dashboard import app as module
    monkeypatch.setattr(module, 'HISTORY_FILE', tmp_path / 'history.json')
    together(workers, lambda i: module.history_add({'id': str(i)}))
    entries = module._load_history()
    assert len(entries) == workers
    assert {e['id'] for e in entries} == {str(i) for i in range(workers)}


def test_concurrent_history_updates_preserve_all_fields(monkeypatch, tmp_path):
    from dashboard import app as module
    monkeypatch.setattr(module, 'HISTORY_FILE', tmp_path / 'history.json')
    module.history_add({'id': 'shared'})
    together(32, lambda i: module.history_update('shared', **{f'field_{i}': i}))
    assert module._load_history() == [{'id': 'shared', **{f'field_{i}': i for i in range(32)}}]
