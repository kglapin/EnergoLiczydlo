"""Ground heat-transfer preparation for the hourly ISO 52016 solver.

The steady slab-on-ground transmittance follows the characteristic-dimension
method of ISO 13370. ISO 13370's normal periodic procedure is monthly; for an
hourly dynamic solver the standard points to Annex D. Therefore certificate
mode requires explicit periodic response coefficients for each ground element
instead of silently fabricating them. Diagnostic mode can derive a transparent
1-D harmonic soil response from measured/project soil properties.
"""

from __future__ import annotations

from math import exp, log, pi, sqrt

import numpy as np

from app.engine.normative_models import GroundElementSettings, GroundISO13370Settings
from app.schemas.models import (
    AdjacentSpaceType,
    BuildingProject,
    ComplianceCheck,
    ElementType,
    OpaqueElement,
)

R_SI_FLOOR_DOWN_M2K_W = 0.17
HOURS_PER_YEAR = 8760.0
SECONDS_PER_YEAR = HOURS_PER_YEAR * 3600.0


def _check(code: str, message: str, *, passed: bool) -> ComplianceCheck:
    return ComplianceCheck(
        name=("Informacja normatywna: " if passed else "Ostrzeżenie normatywne: ") + code,
        passed=passed,
        message=message,
    )


def characteristic_dimension_m(area_m2: float, exposed_perimeter_m: float) -> float:
    """Return the slab characteristic dimension B' = 2A/P [m]."""
    if area_m2 <= 0.0 or exposed_perimeter_m <= 0.0:
        raise ValueError("Ground area and exposed perimeter must be positive")
    return 2.0 * area_m2 / exposed_perimeter_m


def equivalent_thickness_m(
    soil_conductivity_w_mk: float,
    floor_thermal_resistance_m2k_w: float,
    external_wall_thickness_m: float,
) -> float:
    """Equivalent floor thickness d_t [m] used by the ISO 13370 slab method."""
    if soil_conductivity_w_mk <= 0.0 or floor_thermal_resistance_m2k_w <= 0.0:
        raise ValueError("Soil conductivity and floor resistance must be positive")
    if external_wall_thickness_m < 0.0:
        raise ValueError("external_wall_thickness_m must be non-negative")
    return external_wall_thickness_m + soil_conductivity_w_mk * (
        R_SI_FLOOR_DOWN_M2K_W + floor_thermal_resistance_m2k_w
    )


def slab_on_ground_u_value_w_m2k(
    area_m2: float,
    exposed_perimeter_m: float,
    soil_conductivity_w_mk: float,
    floor_thermal_resistance_m2k_w: float,
    external_wall_thickness_m: float,
) -> float:
    """Return ISO 13370 slab-on-ground thermal transmittance [W/(m² K)].

    The two branches are expressed through the characteristic dimension B'
    and the equivalent thickness d_t. This function is intentionally limited
    to slab-on-ground floors; suspended floors and basement assemblies need
    their corresponding ISO 13370 input model rather than reusing this formula.
    """
    b_prime = characteristic_dimension_m(area_m2, exposed_perimeter_m)
    d_t = equivalent_thickness_m(
        soil_conductivity_w_mk,
        floor_thermal_resistance_m2k_w,
        external_wall_thickness_m,
    )
    conductivity = soil_conductivity_w_mk
    if d_t < b_prime:
        return float(2.0 * conductivity / (pi * b_prime + d_t) * log(pi * b_prime / d_t + 1.0))
    return float(conductivity / (0.457 * b_prime + d_t))


def _outdoor_first_harmonic(t_e: np.ndarray) -> tuple[float, float, float]:
    """Return annual mean, first-harmonic amplitude and phase [rad]."""
    values = np.asarray(t_e, dtype=float)
    if values.shape != (8760,):
        raise ValueError("Ground periodic preparation requires 8760 outdoor temperatures")
    mean = float(np.mean(values))
    hours = np.arange(values.size, dtype=float)
    omega = 2.0 * pi / HOURS_PER_YEAR
    centered = values - mean
    cosine = 2.0 / values.size * float(np.sum(centered * np.cos(omega * hours)))
    sine = 2.0 / values.size * float(np.sum(centered * np.sin(omega * hours)))
    amplitude = float(sqrt(cosine * cosine + sine * sine))
    phase = float(np.arctan2(sine, cosine))
    return mean, amplitude, phase


def soil_penetration_depth_m(
    soil_conductivity_w_mk: float,
    soil_density_kg_m3: float,
    soil_specific_heat_j_kgk: float,
) -> float:
    """Annual thermal-wave penetration depth sqrt(2 alpha / omega) [m]."""
    alpha = soil_conductivity_w_mk / (soil_density_kg_m3 * soil_specific_heat_j_kgk)
    omega = 2.0 * pi / SECONDS_PER_YEAR
    return float(sqrt(2.0 * alpha / omega))


def diagnostic_periodic_response(
    effective_depth_m: float,
    soil_conductivity_w_mk: float,
    soil_density_kg_m3: float,
    soil_specific_heat_j_kgk: float,
) -> tuple[float, float]:
    """Return 1-D harmonic attenuation and lag for diagnostic simulations.

    This is a physical semi-infinite-soil solution, not a substitute for
    Annex-D coefficients in certificate mode.
    """
    if effective_depth_m <= 0.0:
        raise ValueError("diagnostic effective depth must be positive")
    penetration = soil_penetration_depth_m(
        soil_conductivity_w_mk,
        soil_density_kg_m3,
        soil_specific_heat_j_kgk,
    )
    ratio = exp(-effective_depth_m / penetration)
    phase_rad = effective_depth_m / penetration
    lag_days = phase_rad / (2.0 * pi) * 365.0
    return float(ratio), float(lag_days)


def periodic_ground_temperature(
    t_e: np.ndarray,
    amplitude_ratio: float,
    phase_shift_days: float,
) -> np.ndarray:
    """Return an 8760-hour equivalent periodic ground temperature [°C]."""
    if not 0.0 <= amplitude_ratio <= 1.0:
        raise ValueError("periodic amplitude ratio must be between 0 and 1")
    mean, amplitude, outdoor_phase = _outdoor_first_harmonic(np.asarray(t_e))
    hours = np.arange(8760, dtype=float)
    omega = 2.0 * pi / HOURS_PER_YEAR
    lag_phase = 2.0 * pi * phase_shift_days / 365.0
    return np.asarray(
        mean + amplitude * amplitude_ratio * np.cos(omega * hours - outdoor_phase - lag_phase),
        dtype=float,
    )


def _element_settings(
    settings: GroundISO13370Settings,
    element_id: str,
) -> GroundElementSettings:
    return settings.elements.get(element_id, GroundElementSettings.model_construct())


def _perimeter_from_geometry(element: OpaqueElement) -> float | None:
    if element.height is None or element.width is None:
        return None
    return 2.0 * (float(element.height) + float(element.width))


def _required_material_values(
    settings: GroundISO13370Settings,
) -> tuple[float, float, float, float]:
    values = (
        settings.soil_conductivity_w_mk,
        settings.soil_density_kg_m3,
        settings.soil_specific_heat_j_kgk,
        settings.external_wall_thickness_m,
    )
    if any(value is None for value in values):
        raise ValueError("Enabled ISO 13370 ground model is missing material properties")
    conductivity, density, specific_heat, wall_thickness = values
    if conductivity is None or density is None or specific_heat is None or wall_thickness is None:
        raise RuntimeError("Ground material input narrowing failed")
    return (
        float(conductivity),
        float(density),
        float(specific_heat),
        float(wall_thickness),
    )


def _periodic_coefficients(
    config: GroundElementSettings,
    settings: GroundISO13370Settings,
    *,
    fallback_depth_m: float,
) -> tuple[float, float, bool]:
    if config.periodic_amplitude_ratio is not None and config.phase_shift_days is not None:
        return config.periodic_amplitude_ratio, config.phase_shift_days, True
    if settings.certificate_mode:
        raise ValueError(
            "Certificate-grade ISO 13370 hourly integration requires explicit "
            "periodic_amplitude_ratio and phase_shift_days for every ground element. "
            "Use coefficients derived from the applicable ISO 13370 Annex-D procedure."
        )
    conductivity, density, specific_heat, _wall_thickness = _required_material_values(settings)
    depth = config.diagnostic_effective_depth_m or fallback_depth_m
    ratio, lag = diagnostic_periodic_response(
        depth,
        conductivity,
        density,
        specific_heat,
    )
    return ratio, lag, False


def prepare_ground_boundaries(
    project: BuildingProject,
    t_e: np.ndarray,
    settings: GroundISO13370Settings,
) -> list[ComplianceCheck]:
    """Attach hourly ground profiles and ISO-13370 slab U-values to a project copy."""
    if not settings.enabled:
        return []

    conductivity, _density, _specific_heat, wall_thickness = _required_material_values(settings)
    checks: list[ComplianceCheck] = []
    found = 0

    for element in project.opaque_building_elements:
        if element.adjacent_space_type != AdjacentSpaceType.GROUND:
            continue
        found += 1
        config = _element_settings(settings, element.id)

        if element.element_type == ElementType.GROUND_FLOOR:
            perimeter = config.exposed_perimeter_m or _perimeter_from_geometry(element)
            if perimeter is None:
                raise ValueError(
                    f"Ground floor '{element.name}' requires exposed_perimeter_m or "
                    "height/width plan dimensions"
                )
            floor_resistance = config.floor_thermal_resistance_m2k_w
            if floor_resistance is None:
                if settings.certificate_mode:
                    raise ValueError(
                        f"Ground floor '{element.name}' requires explicit "
                        "floor_thermal_resistance_m2k_w in certificate mode"
                    )
                floor_resistance = max(
                    1.0 / float(element.u_value) - R_SI_FLOOR_DOWN_M2K_W,
                    1e-6,
                )
                checks.append(
                    _check(
                        "GROUND_RESISTANCE_INFERRED",
                        f"'{element.name}': diagnostic floor resistance was inferred "
                        "from the entered U-value. Enter layer resistance for "
                        "certificate-grade ISO 13370 calculations.",
                        passed=False,
                    )
                )
            b_prime = characteristic_dimension_m(float(element.area), perimeter)
            u_ground = slab_on_ground_u_value_w_m2k(
                float(element.area),
                perimeter,
                conductivity,
                floor_resistance,
                wall_thickness,
            )
            element.u_value = u_ground
            fallback_depth = config.diagnostic_effective_depth_m or max(
                0.25,
                b_prime / 2.0,
            )
        else:
            fallback_depth = config.basement_depth_m or config.diagnostic_effective_depth_m or 1.0
            if settings.certificate_mode and config.basement_depth_m is None:
                raise ValueError(
                    f"Ground-contact element '{element.name}' requires basement_depth_m "
                    "in certificate mode"
                )

        ratio, lag_days, coefficients_verified = _periodic_coefficients(
            config,
            settings,
            fallback_depth_m=fallback_depth,
        )
        profile = periodic_ground_temperature(
            np.asarray(t_e, dtype=float),
            ratio,
            lag_days,
        )
        object.__setattr__(element, "_ground_temperature_profile", profile)
        object.__setattr__(
            element,
            "_ground_periodic_coefficients_verified",
            coefficients_verified,
        )
        periodic_message = (
            "Periodic coefficients supplied explicitly for dynamic use."
            if coefficients_verified
            else (
                "Periodic coefficients are diagnostic 1-D soil-response values, "
                "not Annex-D verification."
            )
        )
        checks.append(
            _check(
                "ISO13370_GROUND_BOUNDARY",
                f"'{element.name}': hourly ground boundary attached; U={element.u_value:.4f} "
                f"W/(m²K), annual periodic amplitude ratio={ratio:.4f}, "
                f"lag={lag_days:.2f} d. {periodic_message}",
                passed=coefficients_verified,
            )
        )

    if found == 0:
        checks.append(
            _check(
                "ISO13370_NO_GROUND_ELEMENTS",
                "ISO 13370 mode is enabled but no opaque element is adjacent to ground.",
                passed=False,
            )
        )
    return checks
