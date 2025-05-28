# 📜 GitHub Copilot – Project Instructions

> These guidelines steer Copilot’s suggestions toward the conventions and tech stack of the **Trading‑Journal‑Auto** project. They are loaded automatically when `github.copilot.useInstructionFiles` is enabled.

---

## 🛠 Tech Stack Defaults

| Domain          | Preferred Choice                                                    |
| --------------- | ------------------------------------------------------------------- |
| **Python**      | ≥ 3.11 using `async` / `await`                                      |
| **Web API**     | FastAPI 0.110 (async)                                               |
| **ORM**         | SQLAlchemy 2.0 **async** style (`AsyncAttrs`, `async_sessionmaker`) |
| **DB**          | SQLite during dev → PostgreSQL in prod                              |
| **Scheduler**   | APScheduler (cron, UTC)                                             |
| **Dashboard**   | Streamlit 1.x + Plotly                                              |
| **Unit Tests**  | `pytest` + `pytest-asyncio`                                         |
| **Lint/Format** | `ruff`, `black` (PEP8)                                              |
| **Container**   | Dockerfile (Alpine/`python:3.11-slim`)                              |

---

## 💡 Coding Guidelines

1. Use **type hints** everywhere (`typing` & PEP 695 where relevant).
2. Add **docstrings** to public functions/classes (Google style).
3. Follow **PEP8** naming: `snake_case` for vars & functions, `PascalCase` for classes.
4. Keep functions < 40 LOC; extract helpers when logic grows.
5. Prefer **list/dict comprehensions** over loops when readability allows.
6. For DB‑queries: always wrap in `async with async_session() as session:`.
7. Handle exceptions with `HTTPException` (FastAPI) or custom `AppError` class.
8. Write at least **one pytest** per feature; aim for ≥ 80 % coverage.

---

## 🔐 Security & Config

- Load secrets via **environment variables** (`dotenv` in dev) – never hard‑code.
- Use `python-dotenv` for local `.env` (excluded via `.gitignore`).
- Hash passwords with **argon2** (`passlib.hash.argon2`) – no plain SHA.

---

## 🔄 Boilerplate Snippets

- **Async SQLAlchemy session**

  ```python
  from sqlalchemy.ext.asyncio import async_sessionmaker
  from app.db import engine

  async_session = async_sessionmaker(engine, expire_on_commit=False)
  ```

- **FastAPI router skeleton**

  ```python
  router = APIRouter(prefix="/trades", tags=["Trades"])

  @router.get("/", response_model=list[TradeOut])
  async def list_trades(user: User = Depends(get_current_user)):
      async with async_session() as db:
          result = await db.scalars(select(Trade).where(Trade.user_id == user.id))
          return result.all()
  ```

---

## 📑 Documentation

- Keep this file concise; update when stack or conventions change.
- Copilot may occasionally deviate—review every PR before merge.
