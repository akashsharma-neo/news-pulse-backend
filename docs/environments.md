# Environment configuration

NewsPulse uses a single switch, **`NEWSMINE_ENV`**, with values `dev` (default), `staging`, or `prod`.

## How it works

1. Copy an env template into [`news-pulse-backend/.env`](../.env) (gitignored).
2. Docker Compose loads `.env` via `env_file` and passes variables into django/celery/celerybeat.
3. [`core/env_config.py`](../core/env_config.py) applies profile defaults **only when a variable is not already set**.
4. Explicit values in `.env` always win over profile defaults.

Frontend uses the same pattern with **`NEXT_PUBLIC_*`** vars in `news-pulse-frontend/.env.local` (see `config/env.*.example`).

## Dev hostname (`NEWSMINE_DEV_HOST`)

One variable drives API, CORS, and allowed-host defaults in [`docker-compose.yml`](../docker-compose.yml):

| Use case | `NEWSMINE_DEV_HOST` |
|----------|---------------------|
| Laptop only | `localhost` |
| Phone on same Wi‑Fi | `<LocalHostName>.local` (mDNS; stable when DHCP changes) |

Print suggested values:

```bash
./scripts/dev-host.sh
```

Set the same hostname in `news-pulse-frontend/.env.local` (`NEXT_PUBLIC_API_URL`, `ALLOWED_DEV_ORIGINS`). Do **not** repeat the LAN IP in four places—change `NEWSMINE_DEV_HOST` only (or run `dev-host.sh` after an IP change).

Optional Mac-only alias: add `192.168.x.x localhostnews` to `/etc/hosts` (`./scripts/dev-host.sh --hosts`). Phones cannot use `/etc/hosts` on your Mac; prefer `.local` for mobile testing.

## Dev (this machine)

```bash
cd news-pulse-backend
cp config/env/dev.example .env

cd ../news-pulse-frontend
cp config/env.dev.example .env.local

cd ../news-pulse-backend
docker compose up -d --build
```

**LM Studio:** start the local server on port `1234` and load `google/gemma-4-e4b`. Containers reach it at `http://host.docker.internal:1234/v1`.

| Variable | Dev value |
|----------|-----------|
| `NEWSMINE_ENV` | `dev` |
| `NEWSMINE_DEV_HOST` | `localhost` (or `YourMac.local` for phone/LAN) |
| `OPENAI_COMPATIBLE_BASE_URL` | `http://host.docker.internal:1234/v1` |
| `OPENAI_COMPATIBLE_MODEL` | `google/gemma-4-e4b` |
| `OPENAI_COMPATIBLE_API_KEY` | `lm-studio` |
| `BASE_URL` / `NEXT_PUBLIC_API_URL` | Derived from `NEWSMINE_DEV_HOST` by compose unless overridden |

## Staging / production

Templates have **blank** LLM and URL fields — fill them in `.env` before deploy:

```bash
cp config/env/staging.example .env   # or prod.example
# edit OPENAI_COMPATIBLE_*, BASE_URL, CORS_ALLOWED_ORIGINS, DB, etc.
docker compose up -d --force-recreate django celery celerybeat
```

For the frontend Docker image after changing `NEXT_PUBLIC_*`:

```bash
docker compose build frontend
docker compose up -d frontend
```

Or run the UI on the host: `cd news-pulse-frontend && npm run dev` (reads `.env.local`).

**Phone / LAN testing:** set `NEWSMINE_DEV_HOST` to your mDNS name, use `docker-compose.lan.example.yml`, and see [production-security.md](production-security.md#lan--phone-testing-dev-only).

## Verify active config

```bash
docker exec np-django python -c "
from django.conf import settings
print('NEWSMINE_ENV=', settings.NEWSMINE_ENV)
print('LLM URL=', settings.OPENAI_COMPATIBLE_BASE_URL)
print('Model=', settings.OPENAI_COMPATIBLE_MODEL)
"
```

## Switching environments

Change values in `.env` (and `.env.local` for the frontend), then recreate containers:

```bash
docker compose up -d --force-recreate django celery celerybeat
```

No code changes are required to switch environments.
