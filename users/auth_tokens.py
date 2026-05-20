"""Shared JWT response helpers for auth endpoints."""

from rest_framework_simplejwt.tokens import RefreshToken

from .models import User


def user_payload(user: User) -> dict:
    return {
        "email": user.email,
        "phone": user.phone,
        "name": user.name,
        "email_verified": user.email_verified,
        "phone_verified": user.phone_verified,
    }


def jwt_response(user: User) -> dict:
    refresh = RefreshToken.for_user(user)
    return {
        "user": user_payload(user),
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }
