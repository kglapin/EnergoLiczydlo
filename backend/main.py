"""Wasmer/FastAPI discovery entry point.

The application implementation remains in ``app.main``; this thin module
exposes the conventional ``main:app`` ASGI target expected by deployment
platforms while preserving the existing local Uvicorn command.
"""

from app.main import app

__all__ = ["app"]
