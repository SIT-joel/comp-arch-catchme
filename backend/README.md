# Catch Me backend (FastAPI + PostgreSQL)

Implements the contract in `docs/INTERFACES.md`. The generated OpenAPI spec is
checked in at `docs/openapi.json` (`python scripts/export_openapi.py`).

## Local setup

```sh
py -3 -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # full pinned freeze
copy .env.example .env                                     # then edit values
```

Start PostgreSQL (from repository root): `docker compose -f infra/docker-compose.yml up -d db`

```sh
.venv/Scripts/python -m alembic upgrade head      # migrations
.venv/Scripts/python seed.py                       # users/pair/devices/rewards
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

Interactive API docs: http://127.0.0.1:8000/docs

## Tests

```sh
.venv/Scripts/python -m pytest tests/unit -q               # pure interval math, no DB
.venv/Scripts/python -m pytest tests/integration -q        # needs PostgreSQL (see conftest)
```

Integration tests run against PostgreSQL via `CM_TEST_DATABASE_URL`
(default `postgresql+psycopg://catch_me:catch_me@localhost:5433/catch_me_test`)
and are SKIPPED with a clear reason when that database is unreachable — a
SQLite-only run does not establish PostgreSQL concurrency behavior.
