# Trading Journal – Auto-IBKR

> **Purpose**
> A professional trading-journal platform designed to track, analyze, and evaluate trading performance.
> The system records trades and executions, calculates performance metrics automatically, and visualizes portfolio performance against market benchmarks such as **SPY** and **QQQ**.

The long-term goal is to evolve this system into a **fully automated trading analytics platform** with broker integrations and advanced portfolio insights.

---

# 📚 Documentation

Additional project documentation:

- **System architecture** → `ARCHITECTURE.md`
- **Domain model** → `DOMAIN_MODEL.md`
- **AI agent rules** → `AGENTS.md`

These documents describe the system design, data model, and development workflow for both developers and AI coding agents.

---

# 🗺 System Overview

Current architecture:

```
Trade Data (manual or imported)
            │
            ▼
      FastAPI Backend
            │
   Business Logic Services
            │
      SQLAlchemy ORM
            │
        Database
   (SQLite → PostgreSQL)
            │
            ▼
     Streamlit Dashboard
            │
            ▼
  Portfolio & Trade Analytics
```

Future architecture will include automated broker ingestion:

```
IBKR API
   │
   ▼
Ingest Service
   │
   ▼
FastAPI Backend
   │
Database + Analytics
   │
Streamlit Dashboard
```

---

# ⚙ Technology Stack

### Backend

- **FastAPI**
- **SQLAlchemy 2 (async)**
- **Pydantic**
- **Alembic migrations**

### Database

- **SQLite** (local development)
- **PostgreSQL** (planned for production)

### Frontend

- **Streamlit**
- **Plotly**

### Market Data

- **yfinance** (SPY, QQQ benchmarks)

### Dev Tools

- **Docker / Docker Compose**
- **Pytest**
- **GitHub Actions CI**
- **AI-assisted development (Codex / Cursor)**

---

# 📂 Repository Structure

```
.
├── README.md
├── ARCHITECTURE.md       # System architecture explanation
├── DOMAIN_MODEL.md       # Core domain entities
├── AGENTS.md             # Rules for AI coding agents
│
├── app/                  # FastAPI backend
│   ├── api/              # HTTP routes
│   ├── services/         # Business logic
│   ├── db/               # models, schemas, session
│   └── core/             # configuration & utilities
│
├── streamlit_app/        # Streamlit dashboard
├── tests/                # unit and integration tests
├── alembic/              # database migrations
│
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .github/workflows/    # CI pipeline
```

---

# 🧠 Core Design Principles

### Fills Are the Source of Truth

Trades are containers for **execution events (fills)**.

This allows the system to correctly handle:

- partial entries
- partial exits
- scaling in/out
- long and short positions

All trade metrics are **calculated automatically from fills**.

---

### Server-Side Calculations

Derived metrics are computed in the backend:

- average entry/exit price
- PnL (USD and %)
- remaining quantity
- trade duration
- intraday classification

This ensures consistency and prevents incorrect manual inputs.

---

### Clean Layered Architecture

The backend follows a clear separation:

```
API layer
   │
Service layer
   │
Persistence layer
   │
Database
```

Business logic lives in **services**, not in API routes.

---

# 🚀 Quick Start (Local Development)

Clone the repository:

```bash
git clone https://github.com/<your-org>/trading-journal.git
cd trading-journal
```

Create virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run database migrations:

```bash
alembic upgrade head
```

Start backend server:

```bash
uvicorn app.main:app --reload
```

Open API docs:

```
http://localhost:8000/docs
```

Start the Streamlit dashboard:

```bash
streamlit run streamlit_app/app.py
```

---

# 🐳 Docker Development

Run the full stack:

```bash
docker compose up --build
```

Services:

- Backend → http://localhost:8000/docs
- Dashboard → http://localhost:8501

---

# 🧪 Testing

Run the test suite:

```bash
pytest -q
```

Tests include:

- API contract validation
- trade calculation logic
- fill lifecycle
- database migrations

---

# 📊 Current Features

- Trade lifecycle management
- Fill-based accounting
- Automatic PnL calculation
- Filtering and querying trades
- Basic analytics dashboard
- Migration-based database evolution

---

# 🔮 Roadmap

Planned improvements:

- Interactive Brokers (IBKR) trade import
- multi-user authentication
- portfolio performance analytics
- benchmark comparison (SPY / QQQ)
- strategy analysis and expectancy metrics
- drawdown and risk analytics
- automated reporting (Telegram / email)

---

# 🔒 Security

- Secrets are not committed to the repository.
- Environment variables are managed via `.env`.
- Passwords stored with **Argon2**.

---

# 🤝 Contributing

Contributions are welcome.

Before submitting a PR:

- follow **PEP8**
- run tests
- keep changes incremental
- maintain separation between API and business logic

## Local Platform Bootstrap (W0-T5)

This repository ships with a 5-service local platform via Docker Compose:

- `api` (FastAPI + Alembic migrations on startup)
- `db` (PostgreSQL 16)
- `redis` (Redis 7)
- `worker` (Celery worker)
- `streamlit` (dashboard)

### Start

```bash
docker compose --env-file .env.example up --build
```

### URLs

- API docs: `http://localhost:8000/docs`
- Streamlit: `http://localhost:8501`
- Postgres: `localhost:5432`
- Redis: `localhost:6379`

### Notes

- For local overrides, copy `.env.example` to `.env` and edit values.
- API and worker share `DATABASE_URL` and `REDIS_URL`.
- Streamlit uses `API_BASE_URL` (defaults to `http://api:8000` in Docker network).

---

## Environment Profiles (`dev/stage/prod`)

Configuration is profile-aware via `APP_ENV` with deterministic precedence:

1. Built-in profile defaults
2. `.env`
3. `.env.<profile>`
4. `.env.local`
5. `.env.<profile>.local`
6. Process environment variables

Notes:
- Use `.env.dev`, `.env.stage`, `.env.prod` for checked-out local profile settings.
- Keep secrets in `.env.local` / `.env.<profile>.local` or real environment variables.
- `APP_SECRET_KEY` is required for `stage` and `prod`; `dev` has a local-only fallback.

---

## Development Workflow

Step-by-step usage:

1. Start environment:
   `powershell -ExecutionPolicy Bypass -File .\scripts\dev_up.ps1`

2. Run tests:
   `powershell -ExecutionPolicy Bypass -File .\scripts\test_stage1_stage2.ps1`

3. Run smoke test:
   `powershell -ExecutionPolicy Bypass -File .\scripts\smoke_import_and_rebuild.ps1`

4. Stop environment:
   `powershell -ExecutionPolicy Bypass -File .\scripts\dev_down.ps1`

Optional:
- Clean reset:
  `powershell -ExecutionPolicy Bypass -File .\scripts\dev_up.ps1 -Reset`

Notes:
- Run Alembic and pytest inside the `api` container, not from the Windows host.
- The scripts already do this for you with `docker compose exec api ...`.
- `dev_up.ps1` starts Docker services, waits for readiness, and runs `alembic upgrade head` inside the container.
- `test_stage1_stage2.ps1` runs the Stage 1 and Stage 2 pytest suites inside the container with `PYTHONPATH=/app`.
- `smoke_import_and_rebuild.ps1` performs a deterministic smoke import and lifecycle rebuild flow against the running local API.
- `dev_down.ps1` stops the stack and supports `-Reset` to remove Docker volumes.
