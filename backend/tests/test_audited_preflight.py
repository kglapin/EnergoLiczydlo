"""Regression tests for geometry/system issues found during the energy audit."""

from __future__ import annotations

import numpy as np
import pytest

from app.engine.audited_calculator import prepare_project_for_audited_calculation
from app.engine.envelope import zone_transmission_network
from app.engine.primary_energy import share_of_renewable_energy
from app.schemas.models import (
    BuildingProject,
    ComplianceCheck,
    OpaqueElement,
    TransparentElement,
)
from scripts.test_building import make_test_project


def _check_codes(checks: list[ComplianceCheck]) -> set[str]:
    return {check.name.split(": ", 1)[-1] for check in checks}


def test_window_is_subtracted_from_gross_host_wall() -> None:
    project = make_test_project()
    corrected, checks = prepare_project_for_audited_calculation(project)

    original_wall = next(
        element
        for element in project.opaque_building_elements
        if element.id == "wall_s"
    )
    corrected_wall = next(
        element
        for element in corrected.opaque_building_elements
        if element.id == "wall_s"
    )

    assert original_wall.area == pytest.approx(40.0)  # caller input is not mutated
    assert corrected_wall.area == pytest.approx(30.0)
    assert "NET_OPAQUE_AREA" in _check_codes(checks)


def test_adding_one_square_metre_of_window_changes_htr_by_uw_minus_uwall() -> None:
    base = make_test_project()
    larger = make_test_project()
    larger.transparent_building_elements[0].area = 11.0

    base_corrected, _ = prepare_project_for_audited_calculation(base)
    larger_corrected, _ = prepare_project_for_audited_calculation(larger)
    climate = np.zeros(8760)

    def h_total(project: BuildingProject) -> float:
        zone_id = project.thermal_zones[0].id
        network = zone_transmission_network(
            project.opaque_building_elements,
            project.transparent_building_elements,
            project.thermal_bridges,
            climate,
            zone_id=zone_id,
        )
        return network.h_total

    # +1 m² opening replaces 1 m² of U=0.25 wall with U=1.00 glazing.
    delta_h = h_total(larger_corrected) - h_total(base_corrected)
    assert delta_h == pytest.approx(0.75)


def test_openings_cannot_exceed_gross_host_area() -> None:
    project = make_test_project()
    project.transparent_building_elements[0].area = 41.0
    with pytest.raises(ValueError, match="exceeds its gross area"):
        prepare_project_for_audited_calculation(project)


def test_ambiguous_opening_host_is_rejected() -> None:
    project = make_test_project()
    project.opaque_building_elements.append(
        OpaqueElement(
            id="wall_s_2",
            name="Druga ściana południowa",
            zone_id="zone_1",
            element_type="external_wall",
            orientation_azimuth=180.0,
            inclination=90.0,
            area=20.0,
            u_value=0.25,
        )
    )
    with pytest.raises(ValueError, match="matches multiple host surfaces"):
        prepare_project_for_audited_calculation(project)


def test_explicit_opening_host_mapping_resolves_ambiguous_geometry() -> None:
    project = make_test_project()
    project.opaque_building_elements.append(
        OpaqueElement(
            id="wall_s_2",
            name="Druga ściana południowa",
            zone_id="zone_1",
            element_type="external_wall",
            orientation_azimuth=180.0,
            inclination=90.0,
            area=20.0,
            u_value=0.35,
        )
    )
    project.metadata["opening_hosts"] = {"win_s": "wall_s"}

    corrected, _ = prepare_project_for_audited_calculation(project)
    host = next(
        element
        for element in corrected.opaque_building_elements
        if element.id == "wall_s"
    )
    other = next(
        element
        for element in corrected.opaque_building_elements
        if element.id == "wall_s_2"
    )
    assert host.area == pytest.approx(30.0)
    assert other.area == pytest.approx(20.0)


def test_incomplete_reference_geometry_produces_warnings() -> None:
    project = make_test_project()
    _, checks = prepare_project_for_audited_calculation(project)
    codes = _check_codes(checks)
    assert "FOOTPRINT_AREA_MISMATCH" in codes  # Af=150 vs roof/floor=90
    assert "LIKELY_INCOMPLETE_WALL_SET" in codes  # only N/S walls


def test_dimensions_remain_authoritative_for_area() -> None:
    wall = OpaqueElement(
        id="wall",
        name="wall",
        zone_id="zone_1",
        height=4.0,
        width=10.0,
        area=999.0,
        u_value=0.2,
    )
    window = TransparentElement(
        id="window",
        name="window",
        zone_id="zone_1",
        height=2.0,
        width=5.0,
        area=999.0,
        u_value=1.0,
        g_value=0.5,
    )
    assert wall.area == pytest.approx(40.0)
    assert window.area == pytest.approx(10.0)


def test_missing_heating_installation_is_explicitly_reported() -> None:
    project = make_test_project()
    project.systems.heating.installation_type = None
    project.systems.heating.auxiliary_energy_kwh_year = None
    _, checks = prepare_project_for_audited_calculation(project)
    assert "HEATING_INSTALLATION_NOT_CLASSIFIED" in _check_codes(checks)


def test_storage_source_without_tank_or_storage_loss_is_reported() -> None:
    project = make_test_project()
    project.systems.dhw.storage_volume_dm3 = None
    project.systems.dhw.storage_efficiency = 1.0
    _, checks = prepare_project_for_audited_calculation(project)
    assert "DHW_STORAGE_LOSSES_NOT_DEFINED" in _check_codes(checks)


def test_missing_thermal_bridges_are_reported() -> None:
    project = make_test_project()
    _, checks = prepare_project_for_audited_calculation(project)
    assert "THERMAL_BRIDGES_NOT_ENTERED" in _check_codes(checks)


def test_ground_and_design_power_limitations_are_reported() -> None:
    project = make_test_project()
    _, checks = prepare_project_for_audited_calculation(project)
    codes = _check_codes(checks)
    assert "GROUND_MODEL_SIMPLIFIED" in codes
    assert "DESIGN_POWER_TMY_PEAK" in codes


def test_all_supported_renewable_carriers_count_in_uoze() -> None:
    energy = {
        "electricity": 500.0,
        "biomass": 100.0,
        "biogas": 100.0,
        "solar": 100.0,
        "wind": 100.0,
        "geothermal": 100.0,
    }
    assert share_of_renewable_energy(energy) == pytest.approx(50.0)
