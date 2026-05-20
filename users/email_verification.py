"""Email verification helpers for password-based signup."""

import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import EmailVerificationToken, User

logger = logging.getLogger(__name__)


def verification_expiry_hours() -> int:
    return int(getattr(settings, "EMAIL_VERIFICATION_EXPIRY_HOURS", 24))


def create_verification_token(user: User) -> EmailVerificationToken:
    """Invalidate prior unused tokens and create a new verification token."""
    EmailVerificationToken.objects.filter(user=user, used_at__isnull=True).delete()
    expires_at = timezone.now() + timedelta(hours=verification_expiry_hours())
    return EmailVerificationToken.objects.create(user=user, expires_at=expires_at)


def build_verification_url(token: EmailVerificationToken) -> str:
    base = getattr(settings, "FRONTEND_URL", "http://localhost:3000").rstrip("/")
    return f"{base}/auth/verify?token={token.token}"


def send_verification_email(user: User, token: EmailVerificationToken) -> None:
    """Send verification link to the user's email. Logs errors instead of raising."""
    verify_url = build_verification_url(token)
    subject = "Verify your NewsPulse email"
    message = (
        f"Hi{(' ' + user.name) if user.name else ''},\n\n"
        f"Thanks for signing up for NewsPulse. Verify your email to start using your account:\n\n"
        f"{verify_url}\n\n"
        f"This link expires in {verification_expiry_hours()} hours.\n\n"
        "If you did not create an account, you can ignore this email."
    )
    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
    except Exception:
        logger.exception(
            "Failed to send verification email to %s (user %s, token %s)",
            user.email, user.pk, token.pk,
        )


def mark_email_verified(user: User) -> None:
    user.email_verified = True
    user.save(update_fields=["email_verified"])
