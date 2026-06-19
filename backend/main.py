from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.storage.database import create_tables
from backend.routes import findings, reports, review
from backend.ws.progress import router as ws_router

log = structlog.get_logger(__name__)

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    log.info("database_initialized")
    yield


app = FastAPI(
    title="Code Review System",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(review.router, prefix="/api")
app.include_router(findings.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(ws_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
