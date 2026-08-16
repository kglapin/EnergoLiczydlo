"""FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import calculate, climate, health

app = FastAPI(
    title="Energoliczydło API",
    description="Backend for building energy performance calculations per PN-EN ISO 52016-1",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api/health", tags=["health"])
app.include_router(calculate.router, prefix="/api/calculate", tags=["calculate"])
app.include_router(climate.router, prefix="/api/climate", tags=["climate"])
