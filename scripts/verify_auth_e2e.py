#!/usr/bin/env python3
"""Manual E2E verification of auth API flows (no Firebase credentials required)."""

import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Same env as run_tests.sh
os.environ.setdefault("DATABASE_HOST", "localhost")
os.environ.setdefault("DATABASE_USER", "akashsharma")
os.environ.setdefault("DATABASE_PASSWORD", "")
os.environ.setdefault("DATABASE_NAME", "newspulse")
os.environ.setdefault("DATABASE_PORT", "5432")
os.environ.setdefault("DJANGO_SECRET_KEY", "test-secret-key-50-chars-minimum-required-for-prod-check-xxx")
os.environ.setdefault("NEWSMINE_ENV", "test")
os.environ.setdefault("EMAIL_BACKEND", "django.core.mail.backends.locmem.EmailBackend")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
os.environ.setdefault("DJANGO_ALLOWED_HOSTS", "testserver,localhost,127.0.0.1")

import django

django.setup()

from rest_framework.test import APIClient

from users.models import EmailVerificationToken, User


def ok(msg: str) -> None:
    print(f"  OK  {msg}")


def fail(msg: str) -> None:
    print(f"  FAIL {msg}")
    sys.exit(1)


def main() -> None:
    client = APIClient()
    email = f"e2e-{uuid.uuid4().hex[:8]}@example.com"
    password = "e2epass12345"

    print("1. Register (no JWT, sends email)")
    res = client.post(
        "/api/auth/register/",
        {
            "email": email,
            "password": password,
            "password_confirm": password,
            "name": "E2E User",
        },
        format="json",
    )
    if res.status_code != 201:
        fail(f"register status {res.status_code}: {res.data}")
    if "access" in res.data:
        fail("register returned access token")
    user = User.objects.get(email=email)
    record = EmailVerificationToken.objects.filter(user=user, used_at__isnull=True).first()
    if not record:
        fail("no verification token created")
    token = str(record.token)
    ok("register + verification token")

    print("2. Login blocked before verify")
    res = client.post("/api/auth/login/", {"email": email, "password": password}, format="json")
    if res.status_code != 403:
        fail(f"expected 403, got {res.status_code}")
    if res.data.get("code") != "email_not_verified":
        fail(f"expected email_not_verified, got {res.data}")
    ok("login blocked with email_not_verified")

    print("3. Verify email → JWT")
    res = client.post("/api/auth/verify-email/", {"token": token}, format="json")
    if res.status_code != 200 or "access" not in res.data:
        fail(f"verify failed: {res.status_code} {res.data}")
    access = res.data["access"]
    refresh = res.data["refresh"]
    ok("verify returns JWT")

    print("4. Login after verify")
    res = client.post("/api/auth/login/", {"email": email, "password": password}, format="json")
    if res.status_code != 200:
        fail(f"login after verify: {res.status_code}")
    ok("login succeeds")

    print("5. GET /api/auth/me/")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    res = client.get("/api/auth/me/")
    if res.status_code != 200 or not res.data.get("email_verified"):
        fail(f"me failed: {res.status_code} {res.data}")
    ok(f"me returns {res.data['email']}")

    print("6. Logout (blacklist refresh)")
    client.credentials()
    res = client.post("/api/auth/logout/", {"refresh": refresh}, format="json")
    if res.status_code != 200:
        fail(f"logout failed: {res.status_code}: {getattr(res, 'data', res.content)}")
    res = client.post("/api/auth/refresh/", {"refresh": refresh}, format="json")
    if res.status_code == 200:
        fail("refresh should fail after logout")
    ok("refresh blacklisted after logout")

    print("7. Refresh token (new login)")
    res = client.post("/api/auth/login/", {"email": email, "password": password}, format="json")
    if res.status_code != 200:
        fail(f"re-login for refresh test: {res.status_code}")
    refresh2 = res.data["refresh"]
    res = client.post("/api/auth/refresh/", {"refresh": refresh2}, format="json")
    if res.status_code != 200 or "access" not in res.data:
        fail(f"refresh failed: {res.status_code}")
    ok("refresh returns new access")

    print("8. Resend verification (generic for unknown)")
    res = client.post(
        "/api/auth/resend-verification/",
        {"email": "nobody@example.com"},
        format="json",
    )
    if res.status_code != 200:
        fail(f"resend failed: {res.status_code}")
    ok("resend returns 200 for unknown email")

    user = User.objects.get(email=email)
    if not user.email_verified:
        fail("user not marked verified")
    if EmailVerificationToken.objects.filter(user=user, used_at__isnull=False).count() < 1:
        fail("verification token not marked used")

    print("\nAll auth E2E checks passed.")


if __name__ == "__main__":
    main()
