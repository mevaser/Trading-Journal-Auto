# Trading Journal – System Architecture

## Overview

The Trading Journal is a backend-first system designed to track, analyze, and evaluate trading performance.

The system is built around a **fill-driven trade accounting model**, where executions (fills) are the source of truth and trade-level metrics are derived from them.

Current architecture:

Client → FastAPI API → Service Layer → SQLAlchemy ORM → Database

The system exposes a REST API used by a lightweight Streamlit frontend.

---

# Core Design Principles

1. **Fills are the source of truth**
2. **Derived metrics are calculated server-side**
3. **Clear separation between API, business logic, and persistence**
4. **Async-first backend architecture**
5. **Strict database migration discipline using Alembic**

---

# High-Level Architecture

## API Layer

Responsible for:

- HTTP routing
- request validation
- response formatting

Files:

app/main.py
app/api/trades.py
app/api/fills.py

Responsibilities:

- expose REST endpoints
- validate requests via Pydantic schemas
- delegate logic to service layer

---

## Service Layer

Responsible for:

- business logic
- trade lifecycle management
- recalculating position metrics

Files:

app/services/trade_service.py
app/services/calculation_service.py

Responsibilities:

- create/update trades
- manage fills
- recompute trade metrics
- enforce business rules

---

## Persistence Layer

Responsible for database interaction.

Files:

app/db/models.py
app/db/session.py

Technology:

- SQLAlchemy (async)
- PostgreSQL (planned)
- SQLite fallback for local dev

Responsibilities:

- ORM entity definitions
- DB session management

---

## Schema Layer

Defines API contracts.

File:

app/db/schemas.py

Technology:

Pydantic

Responsibilities:

- request validation
- response serialization
- API contract stability

---

## Migration Layer

Database schema evolution.

Folder:

alembic/

Responsibilities:

- schema changes
- reproducible DB structure
- versioned migrations

---

# Request Lifecycle Example

Example: Adding a trade fill

Client
↓
POST /trades/{trade_id}/fills
↓
API validates request (Pydantic)
↓
Service inserts fill
↓
calculation_service.recalculate_trade()
↓
Trade metrics updated
↓
Transaction committed
↓
Response returned

---

# Frontend Layer

Current frontend:

Streamlit application

File:

streamlit_app/app.py

Responsibilities:

- visualize trades
- display metrics
- simple UI interaction

Future options:

- React frontend
- analytics dashboards
- SaaS multi-user interface

---

# Deployment (Current)

Local development uses:

Docker + Docker Compose

Files:

Dockerfile
docker-compose.yml

---

# Planned Future Components

1. Broker integrations (Interactive Brokers API)
2. Multi-user authentication
3. Portfolio analytics
4. Strategy analysis
5. Benchmark comparison
6. Advanced dashboards
7. Options and multi-leg trade support

---

# Summary

The system is structured around a clean layered architecture:

API → Services → ORM → Database

Trade accounting is driven by execution fills, ensuring correct handling of partial entries, exits, and complex trading scenarios.
