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
