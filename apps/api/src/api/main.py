import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.db.session import database_lifespan
from api.system.router import router as system_router


def create_app() -> FastAPI:
    app = FastAPI(title="Resolve Flow API", version="0.1.0", lifespan=database_lifespan)

    cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in cors_origins],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(system_router)
    return app


app = create_app()
