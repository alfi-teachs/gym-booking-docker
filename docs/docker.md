# Docker & Compose

## The API image — `api/Dockerfile`

```dockerfile
# ---- Stage 1: build ----
FROM python:3.12-slim AS builder
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- Stage 2: runtime ----
FROM python:3.12-slim
...
RUN apt-get update \
 && apt-get upgrade -y --no-install-recommends \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 1001 appuser
COPY --from=builder /opt/venv /opt/venv
COPY app.py .
USER appuser
HEALTHCHECK ... CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" || exit 1
CMD ["gunicorn", "--preload", "--bind", "0.0.0.0:5000", "--workers", "2", "app:app"]
```

| Part | Purpose |
|---|---|
| **Two stages** | Stage 1 installs dependencies into a virtualenv; stage 2 copies only that virtualenv. Build tools and caches never reach the final image. |
| **`apt-get upgrade`** | Installs Debian security patches released after the base image was built. Done in one `RUN` so it creates one layer, and the apt lists are deleted to save space. |
| **`useradd` + `USER appuser`** | The app runs as an unprivileged user (UID 1001), not root. |
| **`HEALTHCHECK`** | Docker calls `/health` every 30 s and marks the container `healthy` / `unhealthy`. Uses Python's standard library because `curl` isn't in the slim image. |
| **gunicorn** | Production WSGI server. Flask's built-in server is for development only. |
| **`--preload`** | Imports the app once before forking workers, so the database setup (`init_db`) runs once instead of in each worker at the same time. |
| **`.dockerignore`** | Keeps `__pycache__`, `.env` and local virtualenvs out of the build context. |

## The stack — `docker-compose.yml`

```
                 :8080 (only published port)
                    │
   ┌──── frontend ──┼───────────┐
   │             nginx          │
   │                │ /api/*    │
   │               api ─────────┼──── backend ────┐
   └────────────────────────────┘                 │
                                                  db  (volume: db-data)
```

| Feature | How it's configured | Why |
|---|---|---|
| **Service discovery** | Nginx proxies to `http://api:5000`; the API connects to `db:5432` | Compose provides DNS: each service is reachable by its name. |
| **Network segmentation** | `nginx` on `frontend`, `db` on `backend`, `api` on both | The proxy tier cannot reach the database. |
| **Minimal exposure** | Only `nginx` has `ports:`; `db` has none | Postgres is never reachable from the host or the internet. |
| **Startup order** | `depends_on: condition: service_healthy` | Plain `depends_on` waits for a container to *start*. This waits until Postgres passes `pg_isready` and the API passes its healthcheck. |
| **Persistence** | Named volume `db-data` → `/var/lib/postgresql/data` | Bookings survive `docker compose down`. Only `down -v` deletes them. |
| **Configuration** | `${POSTGRES_PASSWORD}` etc. read from `.env` | Secrets stay out of the repo. `.env.example` documents the variables. |
| **Restart policy** | `restart: unless-stopped` | Containers come back after a crash or a Docker restart. |

## Nginx — `nginx/nginx.conf`

- `location /` serves `frontend/index.html`.
- `location /api/` → `proxy_pass http://api:5000/;` — the trailing `/` strips the `/api` prefix, so `/api/classes` reaches the API as `/classes`.
- `X-Forwarded-For` / `X-Real-IP` headers pass the client's real IP to the API.

The browser only ever talks to Nginx, so the frontend and API share one origin and there are no CORS issues.

## Booking concurrency

`POST /bookings` locks the class row with `SELECT … FOR UPDATE` before counting bookings. Without it, two requests arriving together could both see "1 spot left" and both succeed, overbooking the class.

## Useful commands

```bash
docker compose up -d --build     # build and start
docker compose ps                # status and health
docker compose logs -f api       # follow API logs
docker compose exec db psql -U gymuser -d gymdb   # open a SQL shell
docker compose down              # stop, keep data
docker compose down -v           # stop and delete data
```
