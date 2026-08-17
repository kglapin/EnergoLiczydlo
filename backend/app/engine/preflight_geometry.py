"""Envelope preflight checks and gross-to-net area normalisation."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.schemas.models import BuildingProject, ComplianceCheck

AREA_TOLERANCE = 1e-6
ANGLE_TOLERANCE_DEG = 0.1
ENVELOPE_AREA_WARNING_REL = 0.20


def enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def angle_distance(a: float, b: float) -> float:
    delta = abs(float(a) - float(b)) % 360.0
    return min(delta, 360.0 - delta)


def audit_check(
    code: str,
    message: str,
    *,
    passed: bool = False,
) -> ComplianceCheck:
    prefix = "Informacja audytowa" if passed else "Ostrzeżenie audytowe"
    return ComplianceCheck(
        name=f"{prefix}: {code}",
        passed=passed,
        message=message,
    )


def _compatible_host(opening: Any, opaque: Any) -> bool:
    accepted_types = (
        {"roof"}
        if enum_value(opening.element_type) == "skylight"
        else {"external_wall", "basement_wall"}
    )
    if opaque.zone_id != opening.zone_id:
        return False
    if enum_value(opaque.element_type) not in accepted_types:
        return False
    if enum_value(opaque.adjacent_space_type) != "outdoor":
        return False
    inclination_delta = abs(float(opaque.inclination) - float(opening.inclination))
    if inclination_delta > ANGLE_TOLERANCE_DEG:
        return False
    if float(opening.inclination) <= ANGLE_TOLERANCE_DEG:
        return True
    return (
        angle_distance(
            opaque.orientation_azimuth,
            opening.orientation_azimuth,
        )
        <= ANGLE_TOLERANCE_DEG
    )


def opening_host_candidates(project: BuildingProject, opening: Any) -> list[Any]:
    """Resolve an explicit host mapping first, then fall back to geometry matching.

    Advanced/imported projects can set ``metadata.opening_hosts`` as a mapping
    ``{transparent_element_id: opaque_element_id}``. This removes ambiguity
    when multiple wall segments share the same orientation.
    """
    mapping = project.metadata.get("opening_hosts", {})
    explicit_id = mapping.get(opening.id) if isinstance(mapping, dict) else None
    if explicit_id:
        host = next(
            (element for element in project.opaque_building_elements if element.id == explicit_id),
            None,
        )
        if host is None:
            raise ValueError(
                f"Opening host mapping for '{opening.id}' points to unknown "
                f"opaque element '{explicit_id}'."
            )
        if not _compatible_host(opening, host):
            raise ValueError(
                f"Opening host mapping '{opening.id}' -> '{explicit_id}' is "
                "incompatible with zone, boundary type, orientation or inclination."
            )
        return [host]

    return [
        opaque for opaque in project.opaque_building_elements if _compatible_host(opening, opaque)
    ]


def apply_net_opaque_areas(
    project: BuildingProject,
    checks: list[ComplianceCheck],
) -> None:
    """Subtract windows/doors/skylights from a uniquely matched gross host."""
    if not project.transparent_building_elements:
        return

    deductions: dict[str, float] = defaultdict(float)
    hosts: dict[str, Any] = {}
    opening_names: dict[str, list[str]] = defaultdict(list)

    for opening in project.transparent_building_elements:
        candidates = opening_host_candidates(project, opening)
        if not candidates:
            raise ValueError(
                f"Transparent element '{opening.name}' ({opening.id}) has no "
                "exterior host surface with the same zone, orientation and "
                "inclination. Add/correct the corresponding wall or roof."
            )
        if len(candidates) > 1:
            ids = ", ".join(candidate.id for candidate in candidates)
            raise ValueError(
                f"Transparent element '{opening.name}' ({opening.id}) matches "
                f"multiple host surfaces ({ids}). Set metadata.opening_hosts "
                "or make the geometry unambiguous before calculating."
            )
        host = candidates[0]
        hosts[host.id] = host
        deductions[host.id] += float(opening.area)
        opening_names[host.id].append(opening.name)

    for host_id, opening_area in deductions.items():
        host = hosts[host_id]
        gross_area = float(host.area)
        if opening_area > gross_area + AREA_TOLERANCE:
            raise ValueError(
                f"Transparent area {opening_area:.3f} m² assigned to "
                f"'{host.name}' exceeds its gross area {gross_area:.3f} m²."
            )
        net_area = max(0.0, gross_area - opening_area)
        host.area = net_area
        checks.append(
            audit_check(
                "NET_OPAQUE_AREA",
                f"'{host.name}': gross {gross_area:.2f} m² - openings "
                f"{opening_area:.2f} m² ({', '.join(opening_names[host_id])}) "
                f"= net opaque area {net_area:.2f} m².",
                passed=True,
            )
        )


def geometry_checks(project: BuildingProject) -> list[ComplianceCheck]:
    """Return non-blocking consistency warnings for the thermal envelope."""
    checks: list[ComplianceCheck] = []
    storeys = max(int(project.general.number_of_storeys), 1)
    conditioned_area = float(project.general.conditioned_floor_area)
    expected_footprint = conditioned_area / storeys

    roof_area = sum(
        float(element.area)
        for element in project.opaque_building_elements
        if enum_value(element.element_type) == "roof"
        and enum_value(element.adjacent_space_type) == "outdoor"
    )
    bottom_area = sum(
        float(element.area)
        for element in project.opaque_building_elements
        if enum_value(element.element_type) in {"ground_floor", "floor_over_unheated"}
    )

    def rel_diff(value: float, reference: float) -> float:
        return 0.0 if reference <= 0.0 else abs(value - reference) / reference

    if roof_area <= 0.0 or bottom_area <= 0.0:
        checks.append(
            audit_check(
                "INCOMPLETE_ENVELOPE",
                "Envelope is missing a roof/top or floor/bottom boundary "
                f"(roof={roof_area:.2f} m², bottom={bottom_area:.2f} m²).",
            )
        )
    elif (
        rel_diff(roof_area, expected_footprint) > ENVELOPE_AREA_WARNING_REL
        or rel_diff(bottom_area, expected_footprint) > ENVELOPE_AREA_WARNING_REL
    ):
        checks.append(
            audit_check(
                "FOOTPRINT_AREA_MISMATCH",
                f"Af={conditioned_area:.2f} m² and {storeys} storey/storeys "
                f"imply a simple reference footprint of {expected_footprint:.2f} "
                f"m², while roof={roof_area:.2f} m² and bottom boundary="
                f"{bottom_area:.2f} m². Verify zones and envelope geometry.",
            )
        )

    vertical_external = [
        element
        for element in project.opaque_building_elements
        if enum_value(element.element_type) in {"external_wall", "basement_wall"}
        and enum_value(element.adjacent_space_type) == "outdoor"
        and abs(float(element.inclination) - 90.0) <= 5.0
    ]
    directions: list[float] = []
    for element in vertical_external:
        azimuth = float(element.orientation_azimuth) % 360.0
        if not any(angle_distance(azimuth, existing) <= 5.0 for existing in directions):
            directions.append(azimuth)
    if vertical_external and len(directions) < 3:
        checks.append(
            audit_check(
                "LIKELY_INCOMPLETE_WALL_SET",
                f"Only {len(directions)} distinct exterior-wall direction(s) "
                "are present. Verify that all façades were entered.",
            )
        )

    if storeys == 1 and conditioned_area > 0.0 and vertical_external:
        mean_zone_height = float(project.general.heated_volume) / conditioned_area
        wall_heights = [
            float(element.height) for element in vertical_external if element.height is not None
        ]
        if wall_heights:
            mean_wall_height = sum(wall_heights) / len(wall_heights)
            if rel_diff(mean_wall_height, mean_zone_height) > 0.25:
                checks.append(
                    audit_check(
                        "HEIGHT_VOLUME_MISMATCH",
                        "V/Af implies an average conditioned height of "
                        f"{mean_zone_height:.2f} m, while entered exterior "
                        f"walls average {mean_wall_height:.2f} m. Verify "
                        "volume and dimensions.",
                    )
                )

    return checks
