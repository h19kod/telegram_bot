import pytest

from apps.accounts.models import User

pytestmark = pytest.mark.django_db


def test_register_login_refresh_logout(api):
    r = api.post(
        "/api/v1/auth/register",
        {"email": "Owner@Example.com", "password": "Very-Strong-Pass-1", "full_name": "O"},
        format="json",
    )
    assert r.status_code == 201, r.json()
    assert r.json()["user"]["email"] == "owner@example.com"
    assert "sop_refresh" in r.cookies

    r = api.post(
        "/api/v1/auth/login",
        {"identifier": "owner@example.com", "password": "wrong-password"},
        format="json",
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_credentials"

    r = api.post(
        "/api/v1/auth/login",
        {"identifier": "OWNER@example.com", "password": "Very-Strong-Pass-1"},
        format="json",
    )
    assert r.status_code == 200
    access = r.json()["access"]
    csrf = r.cookies["sop_csrf"].value

    api.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    assert api.get("/api/v1/auth/me").json()["email"] == "owner@example.com"
    api.credentials()

    # Refresh without CSRF header fails; with it succeeds and rotates.
    assert api.post("/api/v1/auth/refresh").status_code == 401
    r = api.post("/api/v1/auth/refresh", HTTP_X_CSRF_TOKEN=csrf)
    assert r.status_code == 200
    old_cookie_reuse = r.cookies["sop_refresh"].value
    assert old_cookie_reuse

    r = api.post("/api/v1/auth/logout")
    assert r.status_code == 204


def test_refresh_token_rotation_blocks_reuse(api):
    User.objects.create_user(email="a@x.com", password="Very-Strong-Pass-1")
    r = api.post(
        "/api/v1/auth/login",
        {"identifier": "a@x.com", "password": "Very-Strong-Pass-1"},
        format="json",
    )
    first = r.cookies["sop_refresh"].value
    csrf = r.cookies["sop_csrf"].value
    r = api.post("/api/v1/auth/refresh", HTTP_X_CSRF_TOKEN=csrf)
    assert r.status_code == 200
    api.cookies["sop_refresh"] = first
    api.cookies["sop_csrf"] = csrf
    assert api.post("/api/v1/auth/refresh", HTTP_X_CSRF_TOKEN=csrf).status_code == 401


def test_phone_login_and_weak_password(api):
    r = api.post(
        "/api/v1/auth/register",
        {"phone": "0770 123 4567", "password": "12345678901"},
        format="json",
    )
    assert r.status_code == 400
    r = api.post(
        "/api/v1/auth/register",
        {"phone": "0770 123 4567", "password": "Very-Strong-Pass-1"},
        format="json",
    )
    assert r.status_code == 201
    r = api.post(
        "/api/v1/auth/login",
        {"identifier": "+9647701234567", "password": "Very-Strong-Pass-1"},
        format="json",
    )
    assert r.status_code == 200


def test_totp_flow(api):
    import pyotp

    from apps.accounts.services import decrypt

    user = User.objects.create_user(email="t@x.com", password="Very-Strong-Pass-1")
    from tests.helpers import auth

    auth(api, user)
    api.post("/api/v1/auth/2fa/setup")
    user.refresh_from_db()
    secret = decrypt(user.totp_secret_encrypted)
    assert (
        api.post(
            "/api/v1/auth/2fa/enable", {"otp": pyotp.TOTP(secret).now()}, format="json"
        ).status_code
        == 204
    )
    api.credentials()
    r = api.post(
        "/api/v1/auth/login",
        {"identifier": "t@x.com", "password": "Very-Strong-Pass-1"},
        format="json",
    )
    assert r.json()["error"]["code"] == "otp_required"


def test_unauthenticated_error_format(api):
    r = api.get("/api/v1/auth/me")
    assert r.status_code == 401
    body = r.json()["error"]
    assert body["code"] == "not_authenticated"
    assert body["request_id"]
