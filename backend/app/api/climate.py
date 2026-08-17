"""Climate-data endpoints."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException

from app.data_paths import resolve_tmy_data_dir
from app.engine.climate import ClimateStation, load_epw, nearest_climate_station

router = APIRouter()

DATA_DIR = resolve_tmy_data_dir(__file__)
GEOCODING_API_URL = os.getenv(
    "GEOCODING_API_URL", "https://geocoding-api.open-meteo.com/v1/search"
)


def _station_from_epw(path: Path) -> ClimateStation:
    """Read the station identity and coordinates from an EPW LOCATION row."""
    with path.open(encoding="utf-8") as epw_file:
        fields = epw_file.readline().strip().split(",")

    if len(fields) < 8 or fields[0] != "LOCATION":
        raise ValueError(f"Invalid EPW LOCATION row in {path}")

    return ClimateStation(
        station_id=path.stem,
        name=path.stem.replace("_", " "),
        latitude=float(fields[6]),
        longitude=float(fields[7]),
    )


def _available_stations() -> list[ClimateStation]:
    return [_station_from_epw(path) for path in sorted(DATA_DIR.glob("*.epw"))]


def _station_payload(station: ClimateStation) -> dict[str, str | float]:
    return {
        "id": station.station_id,
        "name": station.name,
        "latitude": station.latitude,
        "longitude": station.longitude,
    }


@lru_cache(maxsize=128)
def _geocode_location(query: str) -> tuple[str, float, float]:
    """Resolve one user-triggered location search and cache repeated searches."""
    try:
        response = httpx.get(
            GEOCODING_API_URL,
            params={
                "name": query,
                "count": 1,
                "language": "pl",
                "format": "json",
                "countryCode": "PL",
            },
            timeout=8.0,
            headers={"User-Agent": "Energoliczydlo/0.1 climate station selector"},
        )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail="Nie udało się połączyć z geokoderem") from exc

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Geokoder zwrócił błąd")

    payload = response.json()
    results = payload.get("results", [])
    if not results:
        raise HTTPException(status_code=404, detail="Nie znaleziono podanej lokalizacji w Polsce")

    match = results[0]
    try:
        latitude = float(match["latitude"])
        longitude = float(match["longitude"])
        matched_location = ", ".join(
            part
            for part in (match.get("name"), match.get("admin1"), match.get("country"))
            if part
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Geokoder zwrócił nieprawidłowe dane") from exc

    return matched_location or query, latitude, longitude


@router.get("/stations")
def list_stations() -> list[dict[str, str | float]]:
    """Return available TMY station IDs based on .epw files in data/tmy."""
    return [_station_payload(station) for station in _available_stations()]


@router.get("/resolve-location")
def resolve_location(location: str) -> dict[str, Any]:
    """Geocode a Polish location and choose the nearest available TMY station."""
    query = " ".join(location.split())
    if len(query) < 2:
        raise HTTPException(
            status_code=422, detail="Podaj lokalizację o długości co najmniej 2 znaków"
        )

    matched_location, latitude, longitude = _geocode_location(query)
    station, distance_km = nearest_climate_station(latitude, longitude, _available_stations())

    return {
        "query": query,
        "matched_location": matched_location,
        "latitude": latitude,
        "longitude": longitude,
        "station": {
            **_station_payload(station),
            "distance_km": round(distance_km, 1),
        },
    }


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
