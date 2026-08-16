"""Climate-data endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from app.engine.climate import load_epw

router = APIRouter()

DATA_DIR = Path(__file__).parents[3] / "data" / "tmy"


@router.get("/stations")
def list_stations() -> list[dict[str, str]]:
    """Return available TMY station IDs based on .epw files in data/tmy."""
    stations = []
    for path in sorted(DATA_DIR.glob("*.epw")):
        stations.append({"id": path.stem, "name": path.stem.replace("_", " ")})
    return stations


@router.get("/stations/{station_id}/summary")
def station_summary(station_id: str) -> dict[str, Any]:
    """Return a quick annual summary for a station."""
    path = DATA_DIR / f"{station_id}.epw"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Station not found")
    df = load_epw(path)
    return {
        "station_id": station_id,
        "mean_temperature": float(df["T_e"].mean()),
        "max_temperature": float(df["T_e"].max()),
        "min_temperature": float(df["T_e"].min()),
        "annual_ghi": float(df["GHI"].sum() / 1000.0),  # kWh/m2
    }
