# DashMet

Multi-platform marketing analytics dashboard. Syncs ad metrics from Meta Ads into a normalized database and serves them through a REST API to a Next.js frontend.

## Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16, React 19, TypeScript 5, Tailwind CSS 4, shadcn/ui 4, TanStack Query 5, Recharts 3 |
| Backend | Python 3.12, FastAPI 0.115, SQLAlchemy 2, Pydantic 2 |
| Workers | Celery + Redis |
| Database | PostgreSQL 16 |
| Container | Docker + Docker Compose |

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (recommended)
- Or: Python 3.11+, Node.js 20+, PostgreSQL 16, Redis 7

---

## Quickstart (Docker)

This is the fastest way to run everything — API, workers, database, and frontend in one command.

**1. Clone and enter the repo**

```bash
git clone <repo-url> dashmet
cd dashmet
```

**2. Set up environment files**

```bash
cp backend/.env.example backend/.env
cp frontend/.env.local.example frontend/.env.local
```

Open `backend/.env` and fill in the required secrets:

```bash
# Generate SECRET_KEY
openssl rand -hex 32

# Generate ENCRYPTION_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**3. Start all services**

```bash
docker compose up
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API docs (dev) | http://localhost:8000/api/docs |
| PostgreSQL | localhost:5432 |
| Redis | localhost:6379 |

To run in the background: `docker compose up -d`  
To stop: `docker compose down`  
To stop and wipe the database: `docker compose down -v`

---

## Local Development (without Docker)

Run each service manually — useful when you want faster reloads or to debug a specific layer.

### 1. Infrastructure

Start PostgreSQL and Redis locally (or keep them running via Docker):

```bash
docker compose up postgres redis
```

### 2. Backend

```bash
cd backend
pip install -r requirements.txt --break-system-packages

# Apply database migrations
alembic upgrade head

# In separate terminals:
uvicorn app.main:app --reload                          # API server  → :8000
celery -A workers.celery_app worker --loglevel=info    # task worker
celery -A workers.celery_app beat --loglevel=info      # scheduler
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev    # → http://localhost:3000
```

---

## Environment Variables

### `backend/.env`

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `SECRET_KEY` | JWT signing key — generate with `openssl rand -hex 32` |
| `ALGORITHM` | JWT algorithm (default: `HS256`) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token TTL (default: `1440` = 24 h) |
| `ENCRYPTION_KEY` | Fernet key for encrypting platform tokens |
| `CORS_ORIGINS` | Comma-separated allowed origins (e.g. `http://localhost:3000`) |
| `ENVIRONMENT` | `development` or `production` |

### `frontend/.env.local`

| Variable | Description |
|---|---|
| `NEXT_PUBLIC_API_URL` | Backend base URL (default: `http://localhost:8000`) |

---

## Common Commands

### Database migrations

```bash
cd backend
alembic revision --autogenerate -m "describe the change"   # create migration
alembic upgrade head                                        # apply all pending
alembic downgrade -1                                        # roll back one
```

### Frontend

```bash
cd frontend
npm run dev      # dev server with hot reload
npm run build    # production build
npm run lint     # ESLint
```

### Add a shadcn/ui component

```bash
cd frontend
npx shadcn@latest add <component-name>   # e.g. button, card, table
```

Components are placed in `src/components/ui/`.

---

## Project Structure

```
dashmet/
├── backend/          FastAPI app + Celery workers (Python)
│   ├── app/          API routes, models, schemas, services
│   ├── workers/      Celery tasks (sync, insights, async jobs, creatives)
│   └── migrations/   Alembic migration files
├── frontend/         Next.js 15 app (TypeScript)
│   └── src/
│       ├── app/      Pages (auth + dashboard routes)
│       ├── components/
│       ├── lib/      API client, query keys, formatters, constants
│       └── stores/   Zustand UI state
├── docs/             Architecture spec documents
└── docker-compose.yml
```

For detailed architecture decisions and specs, see the `docs/` folder:

- `docs/internal-schema-spec.md` — Database schema
- `docs/backend-api-spec.md` — REST API reference
- `docs/frontend-spec.md` — Frontend pages and components
- `docs/sync-worker-spec.md` — Celery worker logic and rate limiting
- `docs/meta-ads-dashboard-api-reference.md` — Meta Graph API reference
- `docs/meta-ads-metrics-reference.md` — Meta metrics field reference
