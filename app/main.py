from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import fills, trades

app = FastAPI(title="Trading Journal API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(trades.router)
app.include_router(fills.router)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Trading Journal API is live"}
