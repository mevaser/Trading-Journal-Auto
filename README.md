# Trading Journal – Auto‑IBKR

> **Purpose**: Automated trading‑journal platform that fetches trades from Interactive Brokers (IBKR), stores them in a SQL database, and visualises portfolio performance against S\&P 500 (SPY) and NASDAQ 100 (QQQ).

---

## 🗺 System Overview

```
IBKR API  ──►  Python Ingest Service  ──►  PostgreSQL/SQLite
                                   │
                                   └──►  FastAPI  ──►  Streamlit Dashboard
                                               │
                                yfinance (SPY, QQQ market data)
```

- **Backend**: FastAPI + SQLAlchemy 2 (async)
- **Scheduler**: APScheduler cron job (daily import)
- **DB**: SQLite (local) → PostgreSQL (Supabase/Render) in future
- **Frontend**: Streamlit + Plotly
- **Dev Experience**: Docker Compose, GitHub Actions CI, Alembic migrations, Cursor AI code‑gen

---

## 📂 Repository Structure _(after first scaffold)_

```
.
├── README.md            ← you are here
├── app/                 ← FastAPI application package
│   ├── api/             ← routers / endpoints
│   ├── core/            ← config, logging, security
│   ├── db/              ← SQLAlchemy models, CRUD, schemas
│   └── scheduler.py     ← daily IBKR import job
├── dashboard/           ← Streamlit app
├── alembic/             ← DB migration scripts
├── docker-compose.yml   ← multi‑service dev stack
├── Dockerfile           ← backend image
├── requirements.txt     ← Python deps
└── .github/workflows/   ← CI pipeline
```

---

## ⚙ Prerequisites

- **Python ≥ 3.11** (local dev)
- **Docker & Docker Compose** (optional but recommended)
- Interactive Brokers **TWS** or **IB Gateway** running with API enabled
- IBKR credentials & API port (default 7497)

---

## 🚀 Quick Start (local, no Docker)

```bash
# clone & enter
$ git clone https://github.com/<your‑org>/trading‑journal.git
$ cd trading‑journal

# create venv & install deps
$ python -m venv .venv && source .venv/bin/activate
$ pip install -r requirements.txt

# set env vars (example)
$ export IB_HOST=127.0.0.1
$ export IB_PORT=7497
$ export IB_CLIENT_ID=1

# run migrations (creates SQLite by default)
$ alembic upgrade head

# start FastAPI dev server
$ uvicorn app.main:app --reload

# launch Streamlit dashboard (in separate shell)
$ streamlit run dashboard/main.py
```

---

## 🐳 Quick Start with Docker

```bash
# build images & start services
$ docker compose up --build
```

Services:

- **backend**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **dashboard**: [http://localhost:8501](http://localhost:8501)
- **db**: persists in `./postgres-data` volume

---

## 🛠 Development Workflow

1. **Generate code with Cursor**

   - Ask Cursor to _"create SQLAlchemy models based on this ERD"_.
   - Prompt: _"docker‑compose with FastAPI(uvicorn) + Postgres 15"_.

2. **Commit early, commit often** (`dev` branch).
3. **Migrations**: `alembic revision --autogenerate -m "init"` → `alembic upgrade head`.
4. **Write/adjust tests** (`pytest`).
5. **Push → GitHub Actions** runs lint + tests + image build.
6. **Merge to `main` when green** – auto‑deploy optional (Render/Supabase).

---

## 🧪 Testing

```bash
pytest -q
```

Includes unit tests for CRUD & API, plus integration test for IBKR ingest (mocked).

---

## 🔒 Security Notes

- Secrets are **NOT** committed – use `.env`, GitHub Secrets, or Render env panel.
- Passwords stored with Argon2.
- API traffic served over HTTPS in production.

---

## ✨ Roadmap

- [ ] Multi‑user auth & role‑based access
- [ ] Advanced analytics (expectancy, Sharpe, drawdowns)
- [ ] Telegram/Email daily summary
- [ ] Deployment template for Supabase + Render

---

## 🤝 Contributing

PRs welcome. Please adhere to PEP8, run `ruff --fix`, and add tests.

---
