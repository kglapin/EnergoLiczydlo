"""Audited calculation entry point.

The numerical 5R1C core remains unchanged. This wrapper validates modelling
completeness, converts gross host surfaces to net opaque areas, makes hidden
assumptions visible in the result, and refuses inputs that would silently
suppress relevant system losses.
"""

from __future__ import annotations

import app.engine.calculator as core_calculator
from app.engine.preflight_geometry import apply_net_opaque_areas, geometry_checks
from app.engine.preflight_systems import (
    model_limit_checks,
    normalise_renewable_carriers,
    system_preflight,
)
from app.schemas.models import BuildingProject, CalculationResult, ComplianceCheck


def prepare_project_for_audited_calculation(
    project: BuildingProject,
) -> tuple[BuildingProject, list[ComplianceCheck]]:
    """Return a corrected deep copy plus audit checks; never mutate caller input."""
    corrected = project.model_copy(deep=True)
    checks: list[ComplianceCheck] = []

    # Consistency checks intentionally use the gross geometry entered by the
    # user. The numerical core receives net opaque areas after openings are
    # matched and subtracted.
    checks.extend(geometry_checks(corrected))
    checks.extend(system_preflight(corrected))
    apply_net_opaque_areas(corrected, checks)
    checks.extend(model_limit_checks(corrected))
    normalise_renewable_carriers(corrected)
    return corrected, checks


def calculate_building_energy(project: BuildingProject) -> CalculationResult:
    """Run the core calculation after audited preflight and prepend audit checks."""
    corrected, checks = prepare_project_for_audited_calculation(project)
    result = core_calculator.calculate_building_energy(corrected)
    result.compliance = checks + list(result.compliance)
    return result
