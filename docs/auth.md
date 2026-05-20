# User authentication (email, Google, phone OTP)

NewsPulse uses **Django JWT** as the session authority. **Firebase Auth** on the client proves identity for Google and phone OTP; the API exchanges a Firebase ID token for NewsPulse access/refresh tokens.

Email/password signup is **Django-only** with mandatory email verification before login.

## API endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/auth/register/` | Public | Create account; sends verification email (no JWT) |
| POST | `/api/auth/verify-email/` | Public | Body `{ "token": "<uuid>" }` → JWT pair |
| POST | `/api/auth/resend-verification/` | Public | Body `{ "email": "..." }` |
| POST | `/api/auth/login/` | Public | Email or phone + password (verified users only) |
| POST | `/api/auth/firebase/` | Public | Body `{ "id_token": "..." }` → JWT pair |
| GET | `/api/auth/me/` | JWT | Profile + quota fields |
| POST | `/api/auth/refresh/` | Public | Refresh access token |
| POST | `/api/auth/logout/` | Public | Blacklist refresh token |

Login returns **403** with `code: email_not_verified` if the account has not verified email.

## Environment variables

### Django API

| Variable | Purpose |
|----------|---------|
| `FRONTEND_URL` | Base URL for verification links (default `http://localhost:3000`) |
| `EMAIL_VERIFICATION_EXPIRY_HOURS` | Token lifetime (default `24`) |
| `EMAIL_*` / `DEFAULT_FROM_EMAIL` | SMTP for verification mail (same as digest) |
| `FIREBASE_CREDENTIALS_JSON` | Firebase service account JSON (inline) |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to service account JSON file |

### Next.js frontend

| Variable | Purpose |
|----------|---------|
| `NEXT_PUBLIC_API_URL` | API base (e.g. `http://127.0.0.1:8000/api`) |
| `NEXT_PUBLIC_FIREBASE_API_KEY` | Firebase web config |
| `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN` | |
| `NEXT_PUBLIC_FIREBASE_PROJECT_ID` | |
| `NEXT_PUBLIC_FIREBASE_APP_ID` | |

## Firebase Console setup

1. Create a Firebase project and enable **Google** and **Phone** sign-in providers.
2. Add authorized domains: `localhost`, your production frontend host.
3. Phone auth on web requires reCAPTCHA; Blaze billing may be required in some regions.
4. Create a **service account** key for the backend (not the web API key).

## Account linking

- **Google** with an email that already exists: links `firebase_uid` and sets `email_verified=True` (including previously unverified email signups).
- **Phone**: creates or updates user by phone; placeholder email `{digits}@newspulse.local`.
- Guest device history is **not** merged on login (by product choice).

## Verify locally

```bash
cd news-pulse-backend
export EMAIL_BACKEND=django.core.mail.backends.locmem.EmailBackend
export FRONTEND_URL=http://localhost:3000
./run_tests.sh users.tests.test_auth
```

Register via API or UI → check `mail.outbox` in tests or console backend in dev → open verify link → login.

## Follow-ups (not in v1)

- Password reset / forgot password
- Link phone account to a real email from profile
- HttpOnly cookie sessions instead of localStorage JWT
