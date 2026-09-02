from fastapi.testclient import TestClient
import pytest

from api.main import create_app
from core.autonomy.engine import AUTONOMY_TAG


def _register_and_login(client: TestClient, email: str) -> str:
    client.post(
        "/auth/register",
        json={"tenant_name": "T", "email": email, "password": "supersecret1"},
    )
    return client.post(
        "/auth/token", data={"username": email, "password": "supersecret1"}
    ).json()["access_token"]


def _autonomy_client(tmp_path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("APEX_MEMORY_DB", str(tmp_path / "memory_vault.db"))
    import api.routers.memory as mem
    import api.routers.autonomy as auto

    mem._vault = None
    auto._engine = None
    return TestClient(create_app())


def test_autonomy_requires_auth(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _autonomy_client(tmp_path, monkeypatch)
    assert client.post("/v1/autonomy/tick", json={"agent": "a", "goal": "g"}).status_code == 401
    assert client.post("/v1/autonomy/prune", json={}).status_code == 401


def test_tick_recalls_and_records(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _autonomy_client(tmp_path, monkeypatch)
    tok = _register_and_login(client, "auto@t.test")
    headers = {"Authorization": f"Bearer {tok}"}

    # First tick: nothing to recall, but the outcome is recorded.
    first = client.post(
        "/v1/autonomy/tick",
        json={"agent": "scout", "goal": "research stripe webhook notes", "outcome": "found 3 hooks"},
        headers=headers,
    )
    assert first.status_code == 200
    body = first.json()
    assert body["recalled"] == []
    assert body["recorded"]["content"].startswith("[scout]")
    assert AUTONOMY_TAG in body["recorded"]["tags"]

    # Second tick with an overlapping goal recalls the first record.
    second = client.post(
        "/v1/autonomy/tick",
        json={"agent": "scout", "goal": "check stripe webhook", "outcome": "ok"},
        headers=headers,
    ).json()
    assert len(second["recalled"]) == 1
    assert second["recalled"][0]["memory_id"] != second["recorded"]["memory_id"]

    # Durable: the record is visible through the plain memory API too.
    hits = client.get("/v1/memory", params={"tag": AUTONOMY_TAG}, headers=headers).json()
    assert len(hits) == 2


def test_prune_ages_out_stale_records_but_keeps_recent(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _autonomy_client(tmp_path, monkeypatch)
    tok = _register_and_login(client, "prune@t.test")
    headers = {"Authorization": f"Bearer {tok}"}

    # Record an old autonomy memory by backdating it directly in the vault.
    rec = client.post(
        "/v1/autonomy/tick",
        json={"agent": "old", "goal": "legacy goal", "outcome": "stale"},
        headers=headers,
    ).json()["recorded"]
    from api.routers.memory import get_vault

    vault = get_vault()  # same connection as the app; backdate to make it stale
    vault._conn.execute(
        "UPDATE memories SET created_at = created_at - 999999 WHERE memory_id = ?",
        (rec["memory_id"],),
    )
    vault._conn.commit()

    # A fresh record that must survive the prune.
    fresh = client.post(
        "/v1/autonomy/tick",
        json={"agent": "new", "goal": "current goal", "outcome": "fresh"},
        headers=headers,
    ).json()["recorded"]

    # Prune with a 1-hour max age and no recent-protection: the stale record
    # dies, the fresh one survives on age.
    resp = client.post(
        "/v1/autonomy/prune",
        json={"max_age_hours": 1, "keep_recent": 0},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["deleted"] == [rec["memory_id"]]
    assert body["kept"] == 1

    ids = [m["memory_id"] for m in client.get("/v1/memory", headers=headers).json()]
    assert rec["memory_id"] not in ids
    assert fresh["memory_id"] in ids

    # Prune never touches non-autonomy memories.
    client.post("/v1/memory", json={"content": "human note"}, headers=headers)
    resp = client.post("/v1/autonomy/prune", json={"max_age_hours": 1}, headers=headers)
    assert resp.json()["deleted"] == []
    hits = client.get("/v1/memory", params={"q": "human note"}, headers=headers).json()
    assert len(hits) == 1


def test_prune_keep_recent_protects_old_records(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _autonomy_client(tmp_path, monkeypatch)
    tok = _register_and_login(client, "protect@t.test")
    headers = {"Authorization": f"Bearer {tok}"}
    rec = client.post(
        "/v1/autonomy/tick",
        json={"agent": "x", "goal": "one goal", "outcome": "y"},
        headers=headers,
    ).json()["recorded"]

    from api.routers.memory import get_vault

    vault = get_vault()
    vault._conn.execute(
        "UPDATE memories SET created_at = created_at - 999999 WHERE memory_id = ?",
        (rec["memory_id"],),
    )
    vault._conn.commit()

    # keep_recent=1 protects the only (old) record.
    resp = client.post(
        "/v1/autonomy/prune",
        json={"max_age_hours": 1, "keep_recent": 1},
        headers=headers,
    ).json()
    assert resp["deleted"] == [] and resp["kept"] == 1