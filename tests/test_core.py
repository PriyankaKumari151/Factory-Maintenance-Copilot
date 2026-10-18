import sqlite3
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from ingestion import clean_events
from retrieval import SOPRetriever
from workflow import build_workflow
from llm_client import GeminiClient


def test_cleaning_rejects_bad_events():
    good = {'event_id': '1', 'machine_id': ' m001 ', 'started_at': '2026-10-01T00:00:00',
            'ended_at': '2026-10-01T00:30:00', 'fault_code': 'BELT_SLIP'}
    raw = pd.DataFrame([good, good.copy(), dict(good, event_id='2', ended_at=''),
                        dict(good, event_id='3', ended_at='2026-09-01'),
                        dict(good, event_id='4', machine_id='UNKNOWN')])
    clean, rejected = clean_events(raw, {'M001'})
    assert len(clean) == 1 and len(rejected) == 4
    assert clean.iloc[0]['machine_id'] == 'M001'
    assert clean.iloc[0]['duration_minutes'] == 30


@pytest.fixture
def tiny_db(tmp_path, monkeypatch):
    import database
    path = tmp_path / 'test.db'
    with sqlite3.connect(path) as con:
        con.execute('CREATE TABLE machines (machine_id TEXT, machine_name TEXT, machine_type TEXT)')
        con.execute("INSERT INTO machines VALUES ('M001','Conveyor','conveyor')")
        con.execute('CREATE TABLE downtime_events (machine_id TEXT, fault_code TEXT, started_at TEXT, duration_minutes REAL)')
        con.executemany('INSERT INTO downtime_events VALUES (?,?,?,?)', [
            ('M001','BELT_SLIP','2026-10-01T00:00:00Z',10),
            ('M001','BELT_SLIP','2026-10-07T23:59:00Z',20),
            ('M001','BELT_SLIP','2026-10-08T00:00:00Z',999)])
    monkeypatch.setattr(database, 'DB', path)
    return path


def test_sql_inclusive_date_boundary(tiny_db):
    from database import downtime_summary
    result = downtime_summary('2026-10-01', '2026-10-07')
    assert result[0]['downtime_minutes'] == 30
    assert result[0]['event_count'] == 2


def test_sql_parameterisation(tiny_db):
    from database import downtime_summary
    assert downtime_summary('2026-10-01', '2026-10-07', "M001' OR 1=1 --") == []


def test_bad_date_range():
    from database import window
    with pytest.raises(ValueError):
        window('2026-10-08', '2026-10-01')


def test_retrieval_metadata_filters():
    r = SOPRetriever('tfidf')
    hits = r.retrieve('packaging seal failure inspection', 'packager', 'SEAL_FAIL')
    assert hits and all(h['document_id'] == 'SOP003' for h in hits)
    assert r.retrieve('belt', fault_code='UNKNOWN_FAULT') == []


def test_tfidf_oov_returns_no_evidence():
    assert SOPRetriever('tfidf').retrieve('quasarxyz') == []


class FakeInventory:
    def get_part(self, part_id):
        return {'part_id': part_id, 'stock_quantity': 0}


def test_combined_workflow(tiny_db, monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    g = build_workflow(SOPRetriever('tfidf'), FakeInventory(), GeminiClient())
    r = g.invoke({'question': 'conveyor belt slip inspection', 'intent': 'combined',
                  'start_date': '2026-10-01', 'end_date': '2026-10-07'})
    assert r['evidence']['selected_machine']['machine_id'] == 'M001'
    assert r['evidence']['inventory'][0]['part_id'] == 'P001'
    assert r['answer']['mode'] == 'offline_extracts'
    assert r['trace'] == ['validated_request', 'sql_analytics', 'sop_retrieval', 'inventory_lookup', 'answer']


def test_no_events_no_guidance(tiny_db, monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    g = build_workflow(SOPRetriever('tfidf'), FakeInventory(), GeminiClient())
    r = g.invoke({'question': 'What should I do?', 'intent': 'combined',
                  'start_date': '2027-01-01', 'end_date': '2027-01-02'})
    assert r['evidence']['sources'] == [] and r['evidence']['inventory'] == []


def test_api_rejects_invalid_input():
    from api import app
    client = TestClient(app)
    assert client.post('/ask', json={'question': 'test', 'start_date': '2026-10-08', 'end_date': '2026-10-01'}).status_code == 422
    assert client.post('/ask', json={'question': 'test', 'machine_id': 'WRONG'}).status_code == 422


def test_ticket_idempotency(tmp_path, monkeypatch):
    import mock_platform
    monkeypatch.setattr(mock_platform, 'DATA', tmp_path)
    client = TestClient(mock_platform.app)
    body = {'machine_id': 'M001', 'fault_code': 'BELT_SLIP', 'description': 'Review belt inspection records.'}
    headers = {'Idempotency-Key': 'request-1'}
    first = client.post('/tickets', json=body, headers=headers)
    second = client.post('/tickets', json=body, headers=headers)
    assert first.status_code == 200
    assert first.json()['ticket_id'] == second.json()['ticket_id']
    changed = client.post('/tickets', json={**body, 'description': 'Different maintenance request.'}, headers=headers)
    assert changed.status_code == 409


def test_inventory_failure_is_explicit(monkeypatch):
    import requests
    from platform_client import InventoryClient
    client = InventoryClient()
    def fail(*args, **kwargs):
        raise requests.ConnectionError('offline')
    monkeypatch.setattr(client.session, 'get', fail)
    assert client.get_part('P003')['error'] == 'Inventory service unavailable'


def test_llm_failure_preserves_evidence_path(monkeypatch):
    import requests
    monkeypatch.setenv('GEMINI_API_KEY', 'test-placeholder')
    monkeypatch.setenv('GEMINI_MODEL', 'test-model')
    def fail(*args, **kwargs):
        raise requests.Timeout()
    monkeypatch.setattr(requests, 'post', fail)
    assert GeminiClient().answer('question', {})['mode'] == 'llm_error'
