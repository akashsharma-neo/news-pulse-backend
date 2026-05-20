"""Firebase ID token verification and user provisioning."""

import json
import os
import re

from django.contrib.auth import get_user_model

User = get_user_model()

_firebase_app = None


def _init_firebase():
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app
    import firebase_admin
    from firebase_admin import credentials

    cred_json = os.environ.get("FIREBASE_CREDENTIALS_JSON", "").strip()
    cred_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if cred_json:
        cred = credentials.Certificate(json.loads(cred_json))
    elif cred_path and os.path.isfile(cred_path):
        cred = credentials.Certificate(cred_path)
    else:
        raise RuntimeError(
            "Firebase credentials not configured. Set FIREBASE_CREDENTIALS_JSON or "
            "GOOGLE_APPLICATION_CREDENTIALS."
        )
    _firebase_app = firebase_admin.initialize_app(cred)
    return _firebase_app


def verify_firebase_id_token(id_token: str) -> dict:
    """Verify Firebase ID token and return decoded claims."""
    _init_firebase()
    from firebase_admin import auth

    return auth.verify_id_token(id_token, check_revoked=True)


def normalize_phone(phone: str) -> str:
    """Normalize phone to E.164-ish format for storage."""
    cleaned = re.sub(r"[\s\-()]", "", phone.strip())
    if cleaned and not cleaned.startswith("+"):
        cleaned = f"+{cleaned}"
    return cleaned


def placeholder_email_for_phone(phone: str) -> str:
    phone_clean = phone.replace(" ", "").replace("-", "").replace("+", "")
    return f"{phone_clean}@newspulse.local"


def _claim_firebase_uid(uid: str, target: User) -> None:
    """Assign firebase_uid to target, clearing it from any other row first."""
    User.objects.filter(firebase_uid=uid).exclude(pk=target.pk).update(firebase_uid=None)
    target.firebase_uid = uid


def resolve_user_from_firebase_claims(claims: dict) -> User:
    """
    Create or update a User from verified Firebase token claims.

    Supports google.com (email) and phone providers.
    """
    uid = claims.get("uid") or claims.get("sub")
    if not uid:
        raise ValueError("Firebase token missing uid.")

    firebase_info = claims.get("firebase", {}) or {}
    sign_in_provider = firebase_info.get("sign_in_provider", "")
    email = (claims.get("email") or "").strip().lower()
    phone = normalize_phone(claims.get("phone_number") or "")

    user = User.objects.filter(firebase_uid=uid).first()

    if sign_in_provider == "google.com":
        if not email:
            raise ValueError("Google sign-in requires an email address.")
        existing = User.objects.filter(email__iexact=email).first()
        if existing:
            if existing.firebase_uid and existing.firebase_uid != uid:
                raise ValueError("This email is linked to another sign-in method.")
            _claim_firebase_uid(uid, existing)
            existing.email_verified = True
            existing.save(update_fields=["firebase_uid", "email_verified"])
            return existing
        if user:
            if user.email and user.email.lower() != email:
                raise ValueError("This Google account is linked to a different email.")
            user.email = email
            user.email_verified = True
            if not user.firebase_uid:
                _claim_firebase_uid(uid, user)
            user.save(update_fields=["email", "email_verified", "firebase_uid"])
            return user
        return User.objects.create_user(
            email=email,
            name=(claims.get("name") or "").strip(),
            password=None,
            email_verified=True,
            firebase_uid=uid,
        )

    if sign_in_provider == "phone":
        if not phone:
            raise ValueError("Phone sign-in requires a phone number.")
        existing = User.objects.filter(phone=phone).first()
        if existing:
            if existing.firebase_uid and existing.firebase_uid != uid:
                raise ValueError("This phone number is linked to another account.")
            _claim_firebase_uid(uid, existing)
            existing.phone_verified = True
            existing.email_verified = True
            existing.save(update_fields=["firebase_uid", "phone_verified", "email_verified"])
            return existing
        if user:
            user.phone = phone
            user.phone_verified = True
            user.email_verified = True
            if not user.firebase_uid:
                _claim_firebase_uid(uid, user)
            user.save(update_fields=["phone", "phone_verified", "email_verified", "firebase_uid"])
            return user
        placeholder_email = placeholder_email_for_phone(phone)
        return User.objects.create_user(
            email=placeholder_email,
            phone=phone,
            password=None,
            email_verified=True,
            phone_verified=True,
            firebase_uid=uid,
        )

    raise ValueError(f"Unsupported Firebase sign-in provider: {sign_in_provider}")
