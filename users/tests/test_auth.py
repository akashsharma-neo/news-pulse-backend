"""
NewsPulse users app tests — authentication, registration, and profile.

Tests cover:
    - User registration (valid / invalid) with email verification
    - Login with email and phone (verified users only)
    - Email verify and resend flows
    - Firebase token exchange (mocked)
    - Get-me endpoint (authenticated)
    - Token refresh
    - Logout (blacklist)
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from users.models import EmailVerificationToken

User = get_user_model()


def create_verified_user(**kwargs):
    """Create a user with email_verified=True for login tests."""
    password = kwargs.pop("password", "securepass123")
    user = User.objects.create_user(password=password, **kwargs)
    user.email_verified = True
    user.save(update_fields=["email_verified"])
    return user


class UserRegistrationTest(TestCase):
    """Tests for user registration."""

    def setUp(self):
        self.client = APIClient()
        self.register_url = "/api/auth/register/"

    def test_register_valid_user(self):
        """A valid registration returns 201 without tokens and sends email."""
        data = {
            "email": "test@example.com",
            "phone": "+1234567890",
            "name": "Test User",
            "password": "securepass123",
            "password_confirm": "securepass123",
        }
        response = self.client.post(self.register_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("detail", response.data)
        self.assertNotIn("access", response.data)
        self.assertNotIn("refresh", response.data)
        self.assertEqual(response.data["user"]["email"], "test@example.com")

        user = User.objects.get(email="test@example.com")
        self.assertFalse(user.email_verified)
        self.assertEqual(EmailVerificationToken.objects.filter(user=user).count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("auth/verify", mail.outbox[0].body)

    def test_register_password_mismatch(self):
        data = {
            "email": "test2@example.com",
            "phone": "+0987654321",
            "name": "Test Two",
            "password": "password123",
            "password_confirm": "different123",
        }
        response = self.client.post(self.register_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password_confirm", response.data)

    def test_register_password_too_short(self):
        data = {
            "email": "short@example.com",
            "phone": "+1111111111",
            "name": "Short Pass",
            "password": "short",
            "password_confirm": "short",
        }
        response = self.client.post(self.register_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)

    def test_register_missing_email(self):
        data = {
            "phone": "+1234567890",
            "name": "No Email",
            "password": "securepass123",
            "password_confirm": "securepass123",
        }
        response = self.client.post(self.register_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_duplicate_email(self):
        create_verified_user(email="dup@example.com", phone="+1234567890", password="securepass123")
        data = {
            "email": "dup@example.com",
            "phone": "+0987654321",
            "name": "Duplicate",
            "password": "securepass456",
            "password_confirm": "securepass456",
        }
        response = self.client.post(self.register_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_without_phone(self):
        data = {
            "email": "nophone@example.com",
            "name": "No Phone",
            "password": "securepass123",
            "password_confirm": "securepass123",
        }
        response = self.client.post(self.register_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email="nophone@example.com")
        self.assertIsNone(user.phone)

    def test_register_then_verify_then_me(self):
        data = {
            "email": "tokentest@example.com",
            "phone": "+1234567890",
            "name": "Token Test",
            "password": "securepass123",
            "password_confirm": "securepass123",
        }
        self.client.post(self.register_url, data, format="json")
        user = User.objects.get(email="tokentest@example.com")
        token = EmailVerificationToken.objects.get(user=user)

        verify_response = self.client.post(
            "/api/auth/verify-email/",
            {"token": str(token.token)},
            format="json",
        )
        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)
        self.assertIn("access", verify_response.data)

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {verify_response.data['access']}")
        me_response = self.client.get("/api/auth/me/")
        self.assertEqual(me_response.status_code, status.HTTP_200_OK)
        self.assertTrue(me_response.data["email_verified"])


class EmailVerificationTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_login_blocked_until_verified(self):
        User.objects.create_user(
            email="unverified@example.com",
            password="securepass123",
            email_verified=False,
        )
        response = self.client.post(
            "/api/auth/login/",
            {"email": "unverified@example.com", "password": "securepass123"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data.get("code"), "email_not_verified")

    def test_resend_verification(self):
        user = User.objects.create_user(
            email="resend@example.com",
            password="securepass123",
            email_verified=False,
        )
        EmailVerificationToken.objects.create(
            user=user,
            expires_at=timezone.now() + timedelta(hours=24),
        )
        response = self.client.post(
            "/api/auth/resend-verification/",
            {"email": "resend@example.com"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)

    def test_resend_unknown_email_generic_response(self):
        response = self.client.post(
            "/api/auth/resend-verification/",
            {"email": "missing@example.com"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 0)

    def test_verify_expired_token(self):
        user = User.objects.create_user(email="expired@example.com", password="securepass123")
        record = EmailVerificationToken.objects.create(
            user=user,
            expires_at=timezone.now() - timedelta(hours=1),
        )
        response = self.client.post(
            "/api/auth/verify-email/",
            {"token": str(record.token)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class FirebaseAuthTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch("users.firebase_service.resolve_user_from_firebase_claims")
    @patch("users.firebase_service.verify_firebase_id_token")
    def test_firebase_google_returns_jwt(self, mock_verify, mock_resolve):
        user = create_verified_user(email="google@example.com", password="x")
        mock_verify.return_value = {"uid": "fb123", "firebase": {"sign_in_provider": "google.com"}}
        mock_resolve.return_value = user

        response = self.client.post(
            "/api/auth/firebase/",
            {"id_token": "fake-token"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        mock_verify.assert_called_once_with("fake-token")

    @patch("users.firebase_service.verify_firebase_id_token")
    def test_google_merges_existing_email_user(self, mock_verify):
        existing = User.objects.create_user(
            email="merge@example.com",
            password="securepass123",
            email_verified=False,
        )
        mock_verify.return_value = {
            "uid": "google-uid-1",
            "email": "merge@example.com",
            "name": "Merge User",
            "firebase": {"sign_in_provider": "google.com"},
        }
        response = self.client.post(
            "/api/auth/firebase/",
            {"id_token": "fake"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        existing.refresh_from_db()
        self.assertEqual(existing.firebase_uid, "google-uid-1")
        self.assertTrue(existing.email_verified)

    def test_google_merge_clears_stale_firebase_uid_holder(self):
        """Email merge must not leave firebase_uid on a different row (unique constraint)."""
        from users.firebase_service import resolve_user_from_firebase_claims

        stale = User.objects.create_user(
            email="stale@newspulse.local",
            password=None,
            firebase_uid="google-uid-conflict",
            email_verified=True,
        )
        target = User.objects.create_user(
            email="merge-target@example.com",
            password="securepass123",
            email_verified=False,
        )
        claims = {
            "uid": "google-uid-conflict",
            "email": "merge-target@example.com",
            "name": "Merge Target",
            "firebase": {"sign_in_provider": "google.com"},
        }
        result = resolve_user_from_firebase_claims(claims)
        self.assertEqual(result.pk, target.pk)
        stale.refresh_from_db()
        target.refresh_from_db()
        self.assertIsNone(stale.firebase_uid)
        self.assertEqual(target.firebase_uid, "google-uid-conflict")
        self.assertTrue(target.email_verified)

    def test_phone_merge_clears_stale_firebase_uid_holder(self):
        from users.firebase_service import resolve_user_from_firebase_claims

        stale = User.objects.create_user(
            email="111@newspulse.local",
            password=None,
            firebase_uid="phone-uid-conflict",
            email_verified=True,
        )
        target = User.objects.create_user(
            email="phone-target@example.com",
            phone="+15551234567",
            password="securepass123",
            email_verified=True,
        )
        claims = {
            "uid": "phone-uid-conflict",
            "phone_number": "+15551234567",
            "firebase": {"sign_in_provider": "phone"},
        }
        result = resolve_user_from_firebase_claims(claims)
        self.assertEqual(result.pk, target.pk)
        stale.refresh_from_db()
        target.refresh_from_db()
        self.assertIsNone(stale.firebase_uid)
        self.assertEqual(target.firebase_uid, "phone-uid-conflict")

    @patch("users.firebase_service.verify_firebase_id_token")
    def test_firebase_phone_creates_user(self, mock_verify):
        mock_verify.return_value = {
            "uid": "phone-uid-1",
            "phone_number": "+919876543210",
            "firebase": {"sign_in_provider": "phone"},
        }
        response = self.client.post(
            "/api/auth/firebase/",
            {"id_token": "fake"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user = User.objects.get(firebase_uid="phone-uid-1")
        self.assertEqual(user.phone, "+919876543210")
        self.assertTrue(user.phone_verified)
        self.assertTrue(user.email_verified)


class UserLoginTest(TestCase):
    """Tests for user login."""

    def setUp(self):
        self.client = APIClient()
        self.login_url = "/api/auth/login/"
        self.user = create_verified_user(
            email="login@example.com",
            phone="+1234567890",
            name="Login User",
            password="loginpass123",
        )

    def test_login_with_email(self):
        data = {"email": "login@example.com", "password": "loginpass123"}
        response = self.client.post(self.login_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertTrue(response.data["user"]["email_verified"])

    def test_login_with_phone(self):
        data = {"phone": "+1234567890", "password": "loginpass123"}
        response = self.client.post(self.login_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_login_invalid_password(self):
        data = {"email": "login@example.com", "password": "wrongpassword"}
        response = self.client.post(self.login_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_nonexistent_user(self):
        data = {"email": "nouser@example.com", "password": "anypass"}
        response = self.client.post(self.login_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_no_credentials(self):
        data = {"password": "anypass"}
        response = self.client.post(self.login_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_no_password(self):
        data = {"email": "login@example.com"}
        response = self.client.post(self.login_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class UserMeTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = create_verified_user(
            email="me@example.com",
            phone="+1234567890",
            name="Me User",
            password="mepassword123",
        )
        self.refresh = RefreshToken.for_user(self.user)
        self.me_url = "/api/auth/me/"

    def test_get_me_authenticated(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.refresh.access_token}")
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["email_verified"])

    def test_get_me_unauthenticated(self):
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class TokenRefreshTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = create_verified_user(
            email="refresh@example.com",
            phone="+1234567890",
            password="refreshtest123",
        )
        self.refresh_url = "/api/auth/refresh/"

    def test_refresh_token(self):
        refresh = RefreshToken.for_user(self.user)
        response = self.client.post(self.refresh_url, {"refresh": str(refresh)}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)


class UserLogoutTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = create_verified_user(
            email="logout@example.com",
            phone="+1234567890",
            password="logoutpass123",
        )
        self.logout_url = "/api/auth/logout/"
        self.refresh = RefreshToken.for_user(self.user)

    def test_logout_valid_token(self):
        data = {"refresh": str(self.refresh)}
        response = self.client.post(self.logout_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class UserIntegrationTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = create_verified_user(
            email="integration@example.com",
            phone="+1234567890",
            name="Integration User",
            password="integration123",
        )

    def test_user_model_auth_fields(self):
        self.assertTrue(hasattr(self.user, "email_verified"))
        self.assertTrue(hasattr(self.user, "firebase_uid"))
        self.assertTrue(hasattr(self.user, "phone_verified"))

    def test_superuser_phone_only(self):
        admin = User.objects.create_superuser(phone="+1987654321", password="adminpass123")
        self.assertTrue(admin.email.endswith("@newspulse.local"))
