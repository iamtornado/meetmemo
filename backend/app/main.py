from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine, Base
from app.api.errors import AppError, app_error_handler, http_exception_handler, general_exception_handler
from app.api.v1 import auth, teams, meetings, transcripts, summaries, search, admin, events

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: create tables on startup."""
    logger.info(f"Starting {settings.APP_NAME}...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created")
    yield
    await engine.dispose()
    logger.info("Application shutdown")


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handlers
app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)


# Register routers
api_v1 = APIRouter()

api_v1.include_router(auth.router)
api_v1.include_router(teams.router)
api_v1.include_router(meetings.router)
api_v1.include_router(transcripts.router)
api_v1.include_router(summaries.router)
api_v1.include_router(search.router)
api_v1.include_router(admin.router)
api_v1.include_router(events.router)

app.mount("/api/v1", api_v1)


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.APP_NAME}
