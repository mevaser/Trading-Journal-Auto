# test_models.py
import asyncio, datetime
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.db.models import Base, User, Trade

async def main():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session() as session:
        u = User(username="alice", email="a@example.com", password_hash="x")
        session.add(u)
        await session.commit()

        t = Trade(
            user_id=u.id,
            symbol="AAPL",
            entry_date=datetime.datetime.now(datetime.timezone.utc),
            entry_price=150,
            quantity=10,
            direction="LONG",
        )
        session.add(t)
        await session.commit()

    # fetch with eager-load to avoid lazy I/O
    async with async_session() as session:
        stmt = select(User).options(selectinload(User.trades)).where(User.id == 1)
        user: User = (await session.scalars(stmt)).one()
        print(user, user.trades)

if __name__ == "__main__":
    asyncio.run(main())
