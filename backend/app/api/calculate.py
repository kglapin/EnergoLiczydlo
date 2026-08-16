"""Calculation endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.engine.calculator import calculate_building_energy
from app.schemas.models import BuildingProject, CalculationResult

router = APIRouter()


@router.post("/", response_model=CalculationResult)
def run_calculation(project: BuildingProject) -> CalculationResult:
    """Run the hourly energy calculation for the supplied building project."""
    try:
        return calculate_building_energy(project)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
