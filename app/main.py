from fastapi import FastAPI
from app.api import trades

app = FastAPI()

app.include_router(trades.router)

@app.get("/")
def root():
    return {"message": "Trading Journal API is live"}
