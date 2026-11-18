from __future__ import annotations

from fastapi import Depends

from occupational_health.api.dependencies.auth import require_admin
from occupational_health.core.security import MemoryAuthStore
from tests.conftest import login


def assert_envelope(response, expected_status: int) -> dict:
    assert response.status_code == expected_status, response.text
    body = response.json()
    assert set(body) == {"code", "message", "data", "request_id"}
    assert body["request_id"]
    assert "Traceback" not in body["message"]
    return body


def test_login_me_logout_and_secure_cookie(client) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"login_name": " admin ", "password": "correct-horse-admin"},
    )
    body = assert_envelope(response, 200)
    assert body["data"]["role"] == "admin"
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=strict" in cookie
    assert "correct-horse" not in cookie

    me = client.get("/api/v1/auth/me")
    assert_envelope(me, 200)
    assert_envelope(client.post("/api/v1/auth/logout"), 200)
    assert_envelope(client.get("/api/v1/auth/me"), 401)


def test_login_is_case_insensitive_and_rejects_bad_password(client) -> None:
    assert_envelope(
        client.post(
            "/api/v1/auth/login",
            json={"login_name": "ADMIN", "password": "wrong"},
        ),
        401,
    )
    assert_envelope(
        client.post(
            "/api/v1/auth/login",
            json={"login_name": "ADMIN", "password": "correct-horse-admin"},
        ),
        200,
    )


def test_account_locks_after_five_failures(client) -> None:
    for _ in range(5):
        client.post(
            "/api/v1/auth/login",
            json={"login_name": "admin", "password": "wrong"},
        )
    body = assert_envelope(
        client.post(
            "/api/v1/auth/login",
            json={"login_name": "admin", "password": "correct-horse-admin"},
        ),
        401,
    )
    assert "锁定" in body["message"]


def test_admin_dependency_is_enforced_on_server(client) -> None:
    @client.app.get("/api/v1/test-admin", dependencies=[Depends(require_admin)])
    def admin_only() -> dict:
        return {"code": "OK", "message": "success", "data": {}, "request_id": "test"}

    login(client, "viewer", "correct-horse-viewer")
    assert_envelope(client.get("/api/v1/test-admin"), 403)
    client.post("/api/v1/auth/logout")
    login(client)
    assert_envelope(client.get("/api/v1/test-admin"), 200)


def test_disabled_user_cannot_use_existing_session(
    client, auth_store: MemoryAuthStore
) -> None:
    login(client)
    auth_store.disable_user("admin")
    assert_envelope(client.get("/api/v1/auth/me"), 401)
