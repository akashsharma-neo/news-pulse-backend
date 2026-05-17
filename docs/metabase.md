# Metabase (local data exploration)

Metabase is included in Docker Compose for browsing NewsPulse Postgres data without writing SQL in a shell.

## Start

```bash
cd news-pulse-backend
docker compose up -d metabase
```

Or bring up the full stack; Metabase starts after Postgres is healthy.

Open **http://127.0.0.1:3001** (override host port with `METABASE_PORT` in `.env`).

First launch: create a Metabase admin user (stored in the `metabase_data` volume, not in NewsPulse Postgres).

## Connect to NewsPulse Postgres

In Metabase → **Admin** → **Databases** → **Add database**:

| Field | Value (Docker Compose defaults) |
|-------|----------------------------------|
| Database type | PostgreSQL |
| Host | `postgres` |
| Port | `5432` |
| Database name | `newspulse` (or your `POSTGRES_DB`) |
| Username | `newsuser` (or your `POSTGRES_USER`) |
| Password | `newssecret` (or your `POSTGRES_PASSWORD`) |

Use the Docker **service name** `postgres` as the host, not `localhost`. Metabase runs on the same Compose network as the database.

Values must match `POSTGRES_*` / `DATABASE_*` in `.env` (see `config/env/dev.example`).

## Notes

- **pgvector** columns may not visualize well in Metabase; hide or exclude those fields in questions if needed.
- Metabase settings live in the `metabase_data` volume. `docker compose down -v` removes it along with other volumes.
- For production, do not expose Metabase on the public internet without auth, TLS, and a strong `METABASE_ENCRYPTION_SECRET_KEY`.
