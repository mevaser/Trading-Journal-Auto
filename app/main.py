from fastapi import FastAPI
from app.api import trades
from app.db.session import engine
from app.db.models import Base


app = FastAPI()

app.include_router(trades.router)

@app.on_event("startup")
async def startup_event():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@app.get("/")
def root():
    return {"message": "Trading Journal API is live"}
