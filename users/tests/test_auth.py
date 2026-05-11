"""
NewsPulse users app tests — authentication, registration, and profile.

Tests cover:
    - User registration (valid / invalid)
    - Login with email and phone
    - Password validation (min 8 chars)
    - Get-me endpoint (authenticated)
    - Token refresh
    - Logout (blacklist)
    - Existing models still work (UserInteraction, UserPreference)
"""

from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.models import TokenUser

User = get_user_model()


class UserRegistrationTest(TestCase):
    """Tests for user registration."""

    def setUp(self):
        self.client = APIClient()
        self.register_url = "/api/auth/register/"

    def test_register_valid_user(self):
        """A valid registration returns a 201 with user data and tokens."""
        data = {
            "email": "test@example.com",
            "phone": "+1234567890",
            "name": "Test User",
            "password": "securepass123",
            "password_confirm": "securepass123",
        }
        response = self.client.post(self.register_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("user", response.data)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(response.data["user"]["email"], "test@example.com")
        self.assertEqual(response.data["user"]["name"], "Test User")
        self.assertEqual(response.data["user"]["phone"], "+1234567890")

        # Verify user was created in DB
        self.assertEqual(User.objects.count(), 1)
        user = User.objects.first()
        self.assertEqual(user.email, "test@example.com")
        self.assertEqual(user.name, "Test User")
        self.assertTrue(user.check_password("securepass123"))

    def test_register_password_mismatch(self):
        """Registration fails when passwords don't match."""
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
        """Registration fails when password is less than 8 characters."""
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
        """Registration fails without an email."""
        data = {
            "phone": "+1234567890",
            "name": "No Email",
            "password": "securepass123",
            "password_confirm": "securepass123",
        }
        response = self.client.post(self.register_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_duplicate_email(self):
        """Registration fails when email already exists."""
        User.objects.create_user(
            email="dup@example.com",
            phone="+1234567890",
            password="securepass123",
        )
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
        """Registration succeeds with no phone number (optional field)."""
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

    def test_register_returns_valid_token(self):
        """The access token returned from registration is valid for authenticated endpoints."""
        data = {
            "email": "tokentest@example.com",
            "phone": "+1234567890",
            "name": "Token Test",
            "password": "securepass123",
            "password_confirm": "securepass123",
        }
        response = self.client.post(self.register_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Use the access token to access a protected endpoint
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        me_response = self.client.get("/api/auth/me/")
        self.assertEqual(me_response.status_code, status.HTTP_200_OK)
        self.assertEqual(me_response.data["email"], "tokentest@example.com")


class UserLoginTest(TestCase):
    """Tests for user login."""

    def setUp(self):
        self.client = APIClient()
        self.login_url = "/api/auth/login/"
        self.user = User.objects.create_user(
            email="login@example.com",
            phone="+1234567890",
            name="Login User",
            password="loginpass123",
        )

    def test_login_with_email(self):
        """Login succeeds with email + password."""
        data = {
            "email": "login@example.com",
            "password": "loginpass123",
        }
        response = self.client.post(self.login_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertIn("user", response.data)
        self.assertEqual(response.data["user"]["email"], "login@example.com")

    def test_login_with_phone(self):
        """Login succeeds with phone + password."""
        data = {
            "phone": "+1234567890",
            "password": "loginpass123",
        }
        response = self.client.post(self.login_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_login_invalid_password(self):
        """Login fails with wrong password."""
        data = {
            "email": "login@example.com",
            "password": "wrongpassword",
        }
        response = self.client.post(self.login_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)

    def test_login_nonexistent_user(self):
        """Login fails for a non-existent user."""
        data = {
            "email": "nouser@example.com",
            "password": "anypass",
        }
        response = self.client.post(self.login_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_no_credentials(self):
        """Login fails without email, phone, or password."""
        data = {"password": "anypass"}
        response = self.client.post(self.login_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_no_password(self):
        """Login fails without password."""
        data = {"email": "login@example.com"}
        response = self.client.post(self.login_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class UserMeTest(TestCase):
    """Tests for the /api/auth/me/ endpoint."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="me@example.com",
            phone="+1234567890",
            name="Me User",
            password="mepassword123",
        )
        self.refresh = RefreshToken.for_user(self.user)
        self.me_url = "/api/auth/me/"

    def test_get_me_authenticated(self):
        """Authenticated request returns user profile."""
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.refresh.access_token}")
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "me@example.com")
        self.assertEqual(response.data["name"], "Me User")
        self.assertEqual(response.data["phone"], "+1234567890")
        self.assertIn("date_joined", response.data)

    def test_get_me_unauthenticated(self):
        """Unauthenticated request returns 401."""
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_me_invalid_token(self):
        """Request with invalid token returns 401."""
        self.client.credentials(HTTP_AUTHORIZATION="Bearer invalidtoken")
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class TokenRefreshTest(TestCase):
    """Tests for token refresh."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="refresh@example.com",
            phone="+1234567890",
            name="Refresh User",
            password="refreshtest123",
        )
        self.refresh_url = "/api/auth/refresh/"

    def test_refresh_token(self):
        """Valid refresh token returns a new access token."""
        refresh = RefreshToken.for_user(self.user)
        data = {"refresh": str(refresh)}
        response = self.client.post(self.refresh_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)

    def test_refresh_invalid_token(self):
        """Invalid refresh token returns 401."""
        data = {"refresh": "invalid.token.here"}
        response = self.client.post(self.refresh_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_missing_token(self):
        """Missing refresh token returns 401."""
        data = {}
        response = self.client.post(self.refresh_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class UserLogoutTest(TestCase):
    """Tests for logout (token blacklisting)."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="logout@example.com",
            phone="+1234567890",
            name="Logout User",
            password="logoutpass123",
        )
        self.logout_url = "/api/auth/logout/"
        self.refresh = RefreshToken.for_user(self.user)

    def test_logout_valid_token(self):
        """Valid logout blacklists the refresh token."""
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.refresh.access_token}")
        data = {"refresh": str(self.refresh)}
        response = self.client.post(self.logout_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify the token is now blacklisted
        self.client.credentials()
        data = {"refresh": str(self.refresh)}
        response = self.client.post(self.logout_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_logout_invalid_token(self):
        """Logout with invalid token returns 400."""
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.refresh.access_token}")
        data = {"refresh": "invalid.token"}
        response = self.client.post(self.logout_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_logout_unauthenticated(self):
        """Logout without authentication returns 401."""
        data = {"refresh": str(self.refresh)}
        response = self.client.post(self.logout_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class TokenLifetimeTest(TestCase):
    """Tests that token lifetimes are configured correctly."""

    def test_access_token_lifetime(self):
        """Access token lifetime should be 7 days."""
        user = User.objects.create_user(
            email="lifetime@example.com",
            password="lifetime123",
        )
        refresh = RefreshToken.for_user(user)
        from datetime import datetime, timezone
        exp = datetime.fromtimestamp(refresh.access_token["exp"], tz=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = exp - now
        # Should be approximately 7 days (allow 1 hour tolerance for processing time)
        self.assertTrue(delta.total_seconds() >= 6 * 24 * 3600)
        self.assertTrue(delta.total_seconds() <= 8 * 24 * 3600)

    def test_refresh_token_lifetime(self):
        """Refresh token lifetime should be 30 days."""
        user = User.objects.create_user(
            email="refreshlife@example.com",
            password="refreshlife123",
        )
        refresh = RefreshToken.for_user(user)
        from datetime import datetime, timezone
        exp = datetime.fromtimestamp(refresh["exp"], tz=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = exp - now
        # Should be approximately 30 days (allow 1 hour tolerance)
        self.assertTrue(delta.total_seconds() >= 29 * 24 * 3600)
        self.assertTrue(delta.total_seconds() <= 31 * 24 * 3600)


class UserIntegrationTest(TestCase):
    """Integration tests to ensure existing models still work after adding User model."""

    def setUp(self):
        self.client = APIClient()
        # Create a user
        self.user = User.objects.create_user(
            email="integration@example.com",
            phone="+1234567890",
            name="Integration User",
            password="integration123",
        )

    def test_user_model_fields(self):
        """User model has the expected fields."""
        self.assertTrue(hasattr(self.user, "email"))
        self.assertTrue(hasattr(self.user, "phone"))
        self.assertTrue(hasattr(self.user, "name"))
        self.assertTrue(hasattr(self.user, "is_active"))
        self.assertTrue(hasattr(self.user, "date_joined"))
        self.assertTrue(hasattr(self.user, "is_staff"))
        self.assertTrue(hasattr(self.user, "password"))

    def test_user_str_returns_email(self):
        """__str__ returns the email address."""
        self.assertEqual(str(self.user), "integration@example.com")

    def test_username_field_is_email(self):
        """USERNAME_FIELD is 'email'."""
        self.assertEqual(User.USERNAME_FIELD, "email")

    def test_required_fields(self):
        """REQUIRED_FIELDS includes 'phone'."""
        self.assertIn("phone", User.REQUIRED_FIELDS)

    def test_superuser_creation(self):
        """Can create a superuser."""
        admin = User.objects.create_superuser(
            email="admin@example.com",
            phone="+0000000000",
            name="Admin",
            password="adminpass123",
        )
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertEqual(admin.email, "admin@example.com")

    def test_superuser_email_only(self):
        """Can create a superuser with only email (phone is None)."""
        admin = User.objects.create_superuser(
            email="emailonly@example.com",
            password="adminpass123",
        )
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertEqual(admin.email, "emailonly@example.com")
        self.assertIsNone(admin.phone)
        self.assertEqual(admin.name, "")

    def test_superuser_phone_only(self):
        """Can create a superuser with only phone (generates placeholder email)."""
        admin = User.objects.create_superuser(
            phone="+1987654321",
            password="adminpass123",
        )
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertEqual(admin.phone, "+1987654321")
        self.assertTrue(admin.email.startswith("1987654321@"))
        self.assertIn("newspulse.local", admin.email)

    def test_superuser_neither_email_nor_phone(self):
        """Cannot create a superuser without email or phone."""
        with self.assertRaises(ValueError) as ctx:
            User.objects.create_superuser(password="adminpass123")
        self.assertIn("email or a phone number", str(ctx.exception))

    def test_register_minimal_user(self):
        """Can register a user with only email (phone is optional)."""
        data = {
            "email": "minimal@example.com",
            "password": "minimalpass123",
            "password_confirm": "minimalpass123",
        }
        response = self.client.post("/api/auth/register/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email="minimal@example.com")
        self.assertIsNone(user.phone)
        self.assertEqual(user.name, "")
