# Django static files in Docker (NewsPulse backend)

## Problem

Gunicorn does **not** serve static files the way `manage.py runserver` does. The Docker image originally did not run `collectstatic`, and nothing served files from `STATIC_ROOT`, so `/static/admin/...` and similar URLs returned **404** even though `django.contrib.staticfiles` was installed.

Using `STATIC_URL = 'static/'` (no leading slash) also breaks admin asset URLs from pages under `/admin/...`: the browser resolves relative `static/...` as `/admin/static/...`, which is wrong.

## What we implemented

1. **WhiteNoise** (`whitenoise` in `requirements.txt`)  
   - Middleware: `whitenoise.middleware.WhiteNoiseMiddleware` immediately after `SecurityMiddleware` in `core/settings.py`.

2. **Image build** (`Dockerfile`)  
   - After copying the app, run `collectstatic --noinput` with a throwaway `DJANGO_SECRET_KEY` so `STATIC_ROOT` (`/app/staticfiles`) is populated in the image.  
   - `chown` so the non-root `app` user can read those files.

3. **Settings**  
   - `STATIC_URL = '/static/'` so generated URLs are absolute from the site root.

## Operations

- **Restart alone is not enough** after changing Python settings or the Dockerfile: `docker compose restart django` reuses the old image. Rebuild and recreate:

  ```bash
  docker compose build django && docker compose up -d django
  ```

- **Compose volume note:** only `./worker` is bind-mounted into the Django container, not `articles/` or `core/`. Code shipped in the image comes from the **last build**; rebuild after editing those packages.

## Verification

From the host (with port 8000 published):

```bash
curl -sI http://127.0.0.1:8000/static/admin/css/base.css
```

Expect `HTTP/1.1 200 OK` and `Content-Type: text/css`.
