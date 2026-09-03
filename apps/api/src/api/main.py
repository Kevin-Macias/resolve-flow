import os

import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Resolve Flow API", version="0.1.0")

cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "resolve-flow-api"}


@app.get("/ready", tags=["system"])
async def readiness() -> dict[str, str]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise HTTPException(status_code=503, detail="DATABASE_URL is not configured")

    try:
        async with await psycopg.AsyncConnection.connect(
            database_url, connect_timeout=3
        ) as connection:
            await connection.execute("SELECT 1")
    except psycopg.Error as error:
        raise HTTPException(
            status_code=503, detail="Database is unavailable"
        ) from error

    return {"status": "ready", "database": "connected"}
