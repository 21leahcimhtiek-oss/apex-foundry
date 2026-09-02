from fastapi.testclient import TestClient
import pytest

from api.main import create_app
from core.kernel.memory.vault import PLAN_RECORD_CAPS


def _register_and_login(client: TestClient, email: str) -> str:
    client.post(
        "/auth/register",
        json={"tenant_name": "T", "email": email, "password": "supersecret1"},
    )
    return client.post(
        "/auth/token", data={"username": email, "password": "supersecret1"}
    ).json()["access_token"]


def _memory_client(tmp_path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("APEX_MEMORY_DB", str(tmp_path / "memory_vault.db"))
    # Reset the router's cached vault so it picks up the tmp DB.
    import api.routers.memory as mem

    mem._vault = None
    return TestClient(create_app())


def test_memory_requires_auth(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _memory_client(tmp_path, monkeypatch)
    assert client.post("/v1/memory", json={"content": "x"}).status_code == 401
    assert client.get("/v1/memory").status_code == 401


def test_memory_create_read_search_delete(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _memory_client(tmp_path, monkeypatch)
    tok = _register_and_login(client, "vault@t.test")
    headers = {"Authorization": f"Bearer {tok}"}

    # create
    resp = client.post(
        "/v1/memory",
        json={"content": "Remember the launch checklist", "tags": ["ops", "launch"]},
        headers=headers,
    )
    assert resp.status_code == 201
    rec = resp.json()
    assert rec["content"] == "Remember the launch checklist"
    assert rec["tags"] == ["ops", "launch"]
    assert rec["memory_id"].startswith("mem_")

    # read
    got = client.get(f"/v1/memory/{rec['memory_id']}", headers=headers)
    assert got.status_code == 200
    assert got.json()["memory_id"] == rec["memory_id"]

    # read unknown → 404
    assert client.get("/v1/memory/mem_nope", headers=headers).status_code == 404

    # second record for search
    client.post("/v1/memory", json={"content": "Stripe webhook notes", "tags": ["billing"]}, headers=headers)

    # search by content
    hits = client.get("/v1/memory", params={"q": "launch"}, headers=headers).json()
    assert len(hits) == 1 and hits[0]["memory_id"] == rec["memory_id"]

    # search by tag
    hits = client.get("/v1/memory", params={"tag": "billing"}, headers=headers).json()
    assert len(hits) == 1 and hits[0]["content"] == "Stripe webhook notes"

    # delete
    resp = client.delete(f"/v1/memory/{rec['memory_id']}", headers=headers)
    assert resp.status_code == 200 and resp.json()["deleted"] is True
    assert client.get(f"/v1/memory/{rec['memory_id']}", headers=headers).status_code == 404
    assert client.delete(f"/v1/memory/{rec['memory_id']}", headers=headers).status_code == 404


def test_memory_tenant_isolation(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _memory_client(tmp_path, monkeypatch)
    tok_a = _register_and_login(client, "a@t.test")
    tok_b = _register_and_login(client, "b@t.test")
    rec = client.post(
        "/v1/memory", json={"content": "secret of A"},
        headers={"Authorization": f"Bearer {tok_a}"},
    ).json()

    # B cannot read, search, or delete A's record.
    hb = {"Authorization": f"Bearer {tok_b}"}
    assert client.get(f"/v1/memory/{rec['memory_id']}", headers=hb).status_code == 404
    assert client.get("/v1/memory", headers=hb).json() == []
    assert client.delete(f"/v1/memory/{rec['memory_id']}", headers=hb).status_code == 404
    # A still sees it.
    ha = {"Authorization": f"Bearer {tok_a}"}
    assert len(client.get("/v1/memory", headers=ha).json()) == 1


def test_memory_persists_in_sqlite(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _memory_client(tmp_path, monkeypatch)
    tok = _register_and_login(client, "persist@t.test")
    headers = {"Authorization": f"Bearer {tok}"}
    client.post("/v1/memory", json={"content": "durable note"}, headers=headers)

    # A fresh app instance against the same DB file still sees the record.
    import api.routers.memory as mem

    mem._vault = None
    client2 = TestClient(create_app())
    hits = client2.get("/v1/memory", headers=headers).json()
    assert len(hits) == 1 and hits[0]["content"] == "durable note"


def test_memory_plan_cap_402(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(PLAN_RECORD_CAPS, "free", 1)
    client = _memory_client(tmp_path, monkeypatch)
    tok = _register_and_login(client, "capped@t.test")
    headers = {"Authorization": f"Bearer {tok}"}
    assert client.post("/v1/memory", json={"content": "one"}, headers=headers).status_code == 201
    resp = client.post("/v1/memory", json={"content": "two"}, headers=headers)
    assert resp.status_code == 402


def test_memory_usage_metering(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _memory_client(tmp_path, monkeypatch)
    tok = _register_and_login(client, "meter@t.test")
    headers = {"Authorization": f"Bearer {tok}"}
    for _ in range(5):
        client.post("/v1/memory", json={"content": "n"}, headers=headers)
    usage = client.get("/chat/usage", headers=headers).json()
    assert usage["used_today"] == 5
    # Free plan allows 10/day: 5 more succeed, the 11th is rejected.
    for _ in range(5):
        assert client.post("/v1/memory", json={"content": "n"}, headers=headers).status_code == 201
    assert client.post("/v1/memory", json={"content": "n"}, headers=headers).status_code == 429