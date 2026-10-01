from fastapi.testclient import TestClient

from ontime.api.main import app

client = TestClient(app)


def test_liveness_needs_no_database():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_readiness_with_database(migrated_engine):
    r = client.get("/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["db"] == "ok"
    assert body["ingest"] == {"last_success_at": None, "lag_s": None}
