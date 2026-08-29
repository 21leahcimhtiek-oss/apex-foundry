"""Auth + multi-tenancy tests. Inference is mocked so no network is used."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.routers import auth as auth_router
from api.routers import chat as chat_router
from core.auth import service as auth_service
from core.kernel.inference import router as inference


@pytest.fixture()
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(inference, "complete", lambda prompt, **kw: "mocked-reply")
    monkeypatch.setattr(chat_router, "_memory", None)  # fresh store per test
    monkeypatch.setattr(auth_router, "_service", None)  # fresh auth per test
    return TestClient(create_app())


@pytest.fixture()
def token(client: TestClient) -> str:
    resp = client.post(
        "/auth/register",
        json={
            "tenant_name": "Acme",
            "email": "owner@acme.test",
            "password": "supersecret1",
        },
    )
    assert resp.status_code == 201
    resp = client.post(
        "/auth/token",
        data={"username": "owner@acme.test", "password": "supersecret1"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


def authed(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_register_login_me(client: TestClient, token: str) -> None:
    me = client.get("/auth/me", headers=authed(token))
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == "owner@acme.test"
    assert body["role"] == "admin"
    assert body["tenant_id"].startswith("tnt_")


def test_register_duplicate_email_409(client: TestClient) -> None:
    payload = {
        "tenant_name": "X",
        "email": "dup@acme.test",
        "password": "supersecret1",
    }
    assert client.post("/auth/register", json=payload).status_code == 201
    assert client.post("/auth/register", json=payload).status_code == 409


def test_bad_login_401(client: TestClient) -> None:
    resp = client.post(
        "/auth/token", data={"username": "owner@acme.test", "password": "wrong"}
    )
    assert resp.status_code == 401


def test_chat_requires_auth(client: TestClient) -> None:
    assert client.post("/chat", json={"message": "hi"}).status_code == 401


def test_chat_with_auth_and_usage(client: TestClient, token: str) -> None:
    resp = client.post(
        "/chat", json={"message": "analyze the market"}, headers=authed(token)
    )
    assert resp.status_code == 200
    assert resp.json()["reply"] == "mocked-reply"
    usage = client.get("/chat/usage", headers=authed(token)).json()
    assert usage["used_today"] == 1
    assert usage["limit"] == auth_service.PLAN_LIMITS["free"]


def test_usage_limit_429(client: TestClient, token: str) -> None:
    limit = auth_service.PLAN_LIMITS["free"]
    for _ in range(limit):
        resp = client.post("/chat", json={"message": "hi"}, headers=authed(token))
        assert resp.status_code == 200
    assert (
        client.post("/chat", json={"message": "hi"}, headers=authed(token)).status_code
        == 429
    )


def test_add_user_and_tenant_isolation(client: TestClient, token: str) -> None:
    # admin adds a member to their tenant
    resp = client.post(
        "/auth/users?email=member@acme.test&password=supersecret1",
        headers=authed(token),
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "member"

    # a second tenant cannot see or affect the first
    resp = client.post(
        "/auth/register",
        json={
            "tenant_name": "Beta",
            "email": "owner@beta.test",
            "password": "supersecret1",
        },
    )
    beta_token = client.post(
        "/auth/token",
        data={"username": "owner@beta.test", "password": "supersecret1"},
    ).json()["access_token"]

    other = client.get("/auth/me", headers=authed(beta_token)).json()
    first = client.get("/auth/me", headers=authed(token)).json()
    assert other["tenant_id"] != first["tenant_id"]

    # member (non-admin) cannot add users
    member_token = client.post(
        "/auth/token",
        data={"username": "member@acme.test", "password": "supersecret1"},
    ).json()["access_token"]
    assert (
        client.post(
            "/auth/users?email=x@acme.test&password=supersecret1",
            headers=authed(member_token),
        ).status_code
        == 403
    )
