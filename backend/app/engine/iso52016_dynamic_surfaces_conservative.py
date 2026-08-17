"""Energy-conserving interior-radiation variant of the dynamic surface solver.

This module is intentionally a thin validation layer over
``iso52016_dynamic_surfaces``. It replaces only the interior long-wave coupling
with a symmetric pairwise network. Pairwise conductances guarantee that every
watt leaving one internal surface enters another one; no net heat can be
created or destroyed by the enclosure radiation approximation.
"""

from __future__ import annotations

import numpy as np

from app.engine import iso52016_dynamic_surfaces as _base
from app.engine.surface_transfer import (
    exterior_convection_coefficient,
    linearized_longwave_coefficient,
    natural_convection_coefficient,
    surface_kind_from_inclination,
)
from app.schemas.models import AdjacentSpaceType

FloatArray = _base.FloatArray
DynamicPrepared = _base.DynamicPrepared


def _add_pairwise_interior_radiation(
    matrix: FloatArray,
    prepared: DynamicPrepared,
    guess: FloatArray,
) -> None:
    """Add a symmetric gray-surface enclosure approximation.

    ``A_i*A_j/A_total`` is the well-mixed enclosure view-factor approximation.
    A symmetric pair coefficient makes reciprocity explicit and guarantees
    exact zero net radiative exchange for the enclosure.
    """
    surfaces = prepared.surfaces
    total_area = prepared.total_surface_area
    for left_position, left in enumerate(surfaces):
        t_left = float(guess[left.index])
        for right in surfaces[left_position + 1 :]:
            t_right = float(guess[right.index])
            eps_left = max(float(left.emissivity), 1e-9)
            eps_right = max(float(right.emissivity), 1e-9)
            effective_emissivity = 1.0 / (1.0 / eps_left + 1.0 / eps_right - 1.0)
            h_pair = float(
                linearized_longwave_coefficient(
                    t_left,
                    t_right,
                    emissivity=effective_emissivity,
                )
            )
            conductance = h_pair * left.area * right.area / total_area
            _base._add_conductance(matrix, left.index, right.index, conductance)


def _surface_matrix_and_rhs(
    *,
    prepared: DynamicPrepared,
    hour: int,
    guess: FloatArray,
    t_e: FloatArray,
    t_sky: FloatArray,
    wind_speed: FloatArray,
    wind_direction: FloatArray,
    h_ve: FloatArray,
    t_supply: FloatArray,
    previous: FloatArray,
    phi_int: FloatArray,
    phi_sol: FloatArray,
) -> tuple[FloatArray, FloatArray]:
    matrix = prepared.static_matrix.copy()
    rhs = prepared.storage * previous
    rhs = _base._arr(
        rhs
        + prepared.internal_vector_convective * phi_int[hour]
        + prepared.internal_radiant_distribution * phi_int[hour]
        + prepared.solar_vector_convective * phi_sol[hour]
        + prepared.solar_radiant_distribution * phi_sol[hour]
    )

    matrix[0, 0] += h_ve[hour]
    rhs[0] += h_ve[hour] * t_supply[hour]
    for bridge in prepared.bridges:
        rhs[0] += bridge.h * bridge.boundary[hour]

    for surface in prepared.surfaces:
        surface_temp = float(guess[surface.index])
        kind = surface_kind_from_inclination(surface.inclination)
        h_ci = float(natural_convection_coefficient(surface_temp - float(guess[0]), kind))
        _base._add_conductance(matrix, 0, surface.index, surface.area * h_ci)

    _add_pairwise_interior_radiation(matrix, prepared, guess)

    for path in prepared.opaque:
        ext = path.exterior_surface
        surface_temp = float(guess[ext])
        boundary_temp = float(path.boundary[hour])
        kind = surface_kind_from_inclination(float(path.element.inclination))
        h_ce = float(
            exterior_convection_coefficient(
                delta_t_k=surface_temp - boundary_temp,
                surface_kind=kind,
                area_m2=float(path.element.area),
                wind_speed_m_s=float(wind_speed[hour]),
                wind_direction_deg=float(wind_direction[hour]),
                surface_azimuth_deg=float(path.element.orientation_azimuth),
                roughness=path.roughness,
                wind_exposed=path.wind_exposed,
            )
        )
        g_ce = float(path.element.area) * h_ce
        matrix[ext, ext] += g_ce
        rhs[ext] += g_ce * boundary_temp + path.solar_w[hour]

        if path.element.adjacent_space_type == AdjacentSpaceType.OUTDOOR:
            view_sky = 0.5 * (1.0 + np.cos(np.deg2rad(float(path.element.inclination))))
            h_re_sky = float(
                linearized_longwave_coefficient(surface_temp, float(t_sky[hour]), path.emissivity)
            )
            h_re_ground = float(
                linearized_longwave_coefficient(surface_temp, float(t_e[hour]), path.emissivity)
            )
            g_sky = float(path.element.area) * view_sky * h_re_sky
            g_ground = float(path.element.area) * (1.0 - view_sky) * h_re_ground
            matrix[ext, ext] += g_sky + g_ground
            rhs[ext] += g_sky * float(t_sky[hour]) + g_ground * float(t_e[hour])

    for path in prepared.windows:
        ext = path.exterior_surface
        surface_temp = float(guess[ext])
        h_ce = float(
            exterior_convection_coefficient(
                delta_t_k=surface_temp - float(t_e[hour]),
                surface_kind="wall",
                area_m2=float(path.element.area),
                wind_speed_m_s=float(wind_speed[hour]),
                wind_direction_deg=float(wind_direction[hour]),
                surface_azimuth_deg=float(path.element.orientation_azimuth),
                roughness=path.roughness,
                wind_exposed=path.wind_exposed,
            )
        )
        g_ce = float(path.element.area) * h_ce
        matrix[ext, ext] += g_ce
        rhs[ext] += g_ce * float(t_e[hour])
        view_sky = 0.5 * (
            1.0 + np.cos(np.deg2rad(float(getattr(path.element, "inclination", 90.0))))
        )
        h_re_sky = float(
            linearized_longwave_coefficient(surface_temp, float(t_sky[hour]), path.emissivity)
        )
        h_re_ground = float(
            linearized_longwave_coefficient(surface_temp, float(t_e[hour]), path.emissivity)
        )
        g_sky = float(path.element.area) * view_sky * h_re_sky
        g_ground = float(path.element.area) * (1.0 - view_sky) * h_re_ground
        matrix[ext, ext] += g_sky + g_ground
        rhs[ext] += g_sky * float(t_sky[hour]) + g_ground * float(t_e[hour])

    return matrix, rhs


# The base solver resolves this helper by module-global lookup at runtime.
_base._surface_matrix_and_rhs = _surface_matrix_and_rhs
solve_zone_iso52016_dynamic_surfaces = _base.solve_zone_iso52016_dynamic_surfaces
