"""Hourly zone solver with explicit massless envelope surface nodes.

This module extends the audited five-capacitance construction model with two
massless surface nodes per opaque element. It is intended for detailed physical
analysis where room/exterior convection and long-wave radiation vary with the
hourly state. The formal Polish monthly certificate engine remains separate.

The construction still contains exactly five capacitive material nodes. The
additional nodes are zero-capacity surfaces that keep surface films and the two
half-cell material resistances physically separate from the material centres.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypeAlias, cast

import numpy as np
from numpy.typing import NDArray

from app.engine.envelope import adjacent_temperature
from app.engine.iso52016_hourly import ISO52016ZoneSolution
from app.engine.surface_transfer import (
    exterior_convection_coefficient,
    linearized_longwave_coefficient,
    natural_convection_coefficient,
    surface_kind_from_inclination,
)
from app.schemas.models import AdjacentSpaceType, OpaqueElement, ThermalBridgeConfig

FloatArray: TypeAlias = NDArray[np.float64]
DT = 3600.0


@dataclass(frozen=True)
class OpaqueDynamicPath:
    element: OpaqueElement
    exterior_surface: int
    material_nodes: tuple[int, int, int, int, int]
    interior_surface: int
    boundary: FloatArray
    exterior_half_h: float
    interior_half_h: float
    core_h: FloatArray
    capacities_j_k: FloatArray
    solar_w: FloatArray
    wind_exposed: bool
    roughness: str
    emissivity: float


@dataclass(frozen=True)
class WindowDynamicPath:
    element: Any
    exterior_surface: int
    interior_surface: int
    boundary: FloatArray
    core_h: float
    wind_exposed: bool
    roughness: str
    emissivity: float


@dataclass(frozen=True)
class InteriorSurface:
    element_id: str
    index: int
    area: float
    inclination: float
    emissivity: float


@dataclass(frozen=True)
class BridgeDynamicPath:
    h: float
    boundary: FloatArray


@dataclass(frozen=True)
class DynamicPrepared:
    storage: FloatArray
    static_matrix: FloatArray
    opaque: tuple[OpaqueDynamicPath, ...]
    windows: tuple[WindowDynamicPath, ...]
    surfaces: tuple[InteriorSurface, ...]
    bridges: tuple[BridgeDynamicPath, ...]
    internal_vector_convective: FloatArray
    internal_radiant_distribution: FloatArray
    solar_vector_convective: FloatArray
    solar_radiant_distribution: FloatArray
    hvac_vector: FloatArray
    operative_vector: FloatArray
    total_surface_area: float


def _arr(value: Any) -> FloatArray:
    return cast(FloatArray, np.asarray(value, dtype=np.float64))


def _hourly(value: float | FloatArray, n: int, name: str) -> FloatArray:
    result = _arr(value)
    if result.ndim == 0:
        result = _arr(np.full(n, float(result)))
    if result.shape != (n,) or not np.isfinite(result).all():
        raise ValueError(f"{name} must be scalar or one finite value per hour")
    return result


def _distribution(
    surfaces: Sequence[InteriorSurface],
    explicit: Mapping[str, float] | None,
) -> FloatArray:
    if explicit:
        known = {surface.element_id for surface in surfaces}
        unknown = set(explicit) - known
        if unknown:
            raise ValueError(
                "Unknown surface IDs in radiant distribution: " + ", ".join(sorted(unknown))
            )
        values = _arr([float(explicit.get(surface.element_id, 0.0)) for surface in surfaces])
        if np.any(values < 0.0) or not np.isclose(values.sum(), 1.0, atol=1e-6):
            raise ValueError("Radiant distribution factors must be non-negative and sum to 1")
        return values
    areas = _arr([surface.area for surface in surfaces])
    return cast(FloatArray, areas / areas.sum())


def _bridge_paths(
    bridges: ThermalBridgeConfig,
    zone_id: str,
    t_e: FloatArray,
    opaque: Mapping[str, OpaqueElement],
) -> tuple[BridgeDynamicPath, ...]:
    result: list[BridgeDynamicPath] = []
    for bridge in [*bridges.linear_bridges, *bridges.point_bridges]:
        if bridge.zone_id != zone_id:
            continue
        h = (
            float(bridge.psi_value) * float(bridge.length)
            if hasattr(bridge, "psi_value")
            else float(bridge.chi_value) * int(bridge.count)
        )
        if h <= 0.0:
            continue
        host_id = getattr(bridge, "element_id", None)
        host = opaque.get(host_id) if isinstance(host_id, str) else None
        adjacent = getattr(bridge, "adjacent_space_type", None) or (
            host.adjacent_space_type if host else AdjacentSpaceType.OUTDOOR
        )
        if adjacent == AdjacentSpaceType.HEATED_ZONE:
            continue
        if host is not None and adjacent != AdjacentSpaceType.OUTDOOR:
            boundary = _arr(adjacent_temperature(host, t_e))
        elif adjacent == AdjacentSpaceType.CONSTANT_TEMPERATURE:
            value = getattr(bridge, "adjacent_temperature", None)
            if value is None:
                raise ValueError(f"Bridge '{bridge.id}' requires adjacent_temperature")
            boundary = _arr(np.full(len(t_e), float(value)))
        else:
            boundary = t_e
        result.append(BridgeDynamicPath(h=h, boundary=boundary))
    return tuple(result)


def _prepare_dynamic(
    *,
    opaque_elements: list[OpaqueElement],
    transparent_elements: Sequence[Any],
    bridges: ThermalBridgeConfig,
    zone_id: str,
    t_e: FloatArray,
    opaque_solar: Mapping[str, FloatArray],
    air_capacity_j_k: float,
    opaque_boundary_resistances_m2k_w: Mapping[str, tuple[float, float]],
    window_core_resistances_m2k_w: Mapping[str, float],
    wind_exposed_by_element: Mapping[str, bool],
    roughness_by_element: Mapping[str, str],
    emissivity_by_element: Mapping[str, float],
    internal_convective_fraction: float,
    solar_convective_fraction: float,
    hvac_convective_fraction: float,
    operative_air_weight: float,
    solar_distribution: Mapping[str, float] | None,
) -> DynamicPrepared:
    selected_opaque = [element for element in opaque_elements if element.zone_id == zone_id]
    selected_windows = [element for element in transparent_elements if element.zone_id == zone_id]

    exact_opaque: list[OpaqueElement] = []
    for element in selected_opaque:
        if element.adjacent_space_type == AdjacentSpaceType.HEATED_ZONE:
            continue
        resistances = getattr(element, "thermal_node_resistances_m2k_w", None)
        capacities = getattr(element, "thermal_node_capacities_kj_m2k", None)
        if resistances is None or len(resistances) != 4:
            raise ValueError(
                f"Dynamic surface solver requires four material-node core resistances for '{element.id}'"
            )
        if capacities is None or len(capacities) != 5:
            raise ValueError(
                f"Dynamic surface solver requires five material-node capacities for '{element.id}'"
            )
        if element.id not in opaque_boundary_resistances_m2k_w:
            raise ValueError(
                f"Dynamic surface solver requires exterior/interior half-cell resistances for '{element.id}'"
            )
        exact_opaque.append(element)

    n_nodes = 1 + 7 * len(exact_opaque) + 2 * len(selected_windows)
    storage = _arr(np.zeros(n_nodes))
    storage[0] = float(air_capacity_j_k) / DT
    static_matrix = _arr(np.zeros((n_nodes, n_nodes)))
    static_matrix[0, 0] += storage[0]

    opaque_paths: list[OpaqueDynamicPath] = []
    window_paths: list[WindowDynamicPath] = []
    surfaces: list[InteriorSurface] = []
    cursor = 1

    for element in exact_opaque:
        area = float(element.area)
        ext_surface = cursor
        material = cast(tuple[int, int, int, int, int], tuple(range(cursor + 1, cursor + 6)))
        int_surface = cursor + 6
        cursor += 7

        core_r = _arr(element.thermal_node_resistances_m2k_w)
        capacities = _arr(element.thermal_node_capacities_kj_m2k) * area * 1000.0
        r_ext_half, r_int_half = opaque_boundary_resistances_m2k_w[element.id]
        if r_ext_half <= 0.0 or r_int_half <= 0.0 or np.any(core_r <= 0.0):
            raise ValueError(f"All material resistances for '{element.id}' must be positive")
        if np.any(capacities < 0.0) or capacities.sum() <= 0.0:
            raise ValueError(f"Material capacities for '{element.id}' must be non-negative")

        h_ext_half = area / float(r_ext_half)
        h_int_half = area / float(r_int_half)
        core_h = area / core_r

        for local, node in enumerate(material):
            storage[node] = capacities[local] / DT
            static_matrix[node, node] += storage[node]

        static_matrix[ext_surface, ext_surface] += h_ext_half
        static_matrix[material[0], material[0]] += h_ext_half
        static_matrix[ext_surface, material[0]] -= h_ext_half
        static_matrix[material[0], ext_surface] -= h_ext_half

        for link, h_value in enumerate(core_h):
            left, right = material[link], material[link + 1]
            static_matrix[left, left] += h_value
            static_matrix[right, right] += h_value
            static_matrix[left, right] -= h_value
            static_matrix[right, left] -= h_value

        static_matrix[material[-1], material[-1]] += h_int_half
        static_matrix[int_surface, int_surface] += h_int_half
        static_matrix[material[-1], int_surface] -= h_int_half
        static_matrix[int_surface, material[-1]] -= h_int_half

        boundary = _arr(adjacent_temperature(element, t_e))
        solar = _hourly(
            opaque_solar.get(element.id, np.zeros(len(t_e))),
            len(t_e),
            f"solar {element.id}",
        )
        emissivity = float(emissivity_by_element.get(element.id, 0.9))
        if not 0.0 <= emissivity <= 1.0:
            raise ValueError(f"Emissivity for '{element.id}' must be 0..1")
        surfaces.append(
            InteriorSurface(
                element_id=element.id,
                index=int_surface,
                area=area,
                inclination=float(element.inclination),
                emissivity=emissivity,
            )
        )
        opaque_paths.append(
            OpaqueDynamicPath(
                element=element,
                exterior_surface=ext_surface,
                material_nodes=material,
                interior_surface=int_surface,
                boundary=boundary,
                exterior_half_h=h_ext_half,
                interior_half_h=h_int_half,
                core_h=core_h,
                capacities_j_k=capacities,
                solar_w=solar,
                wind_exposed=bool(wind_exposed_by_element.get(element.id, True)),
                roughness=roughness_by_element.get(element.id, "rough"),
                emissivity=emissivity,
            )
        )

    for element in selected_windows:
        if element.id not in window_core_resistances_m2k_w:
            raise ValueError(f"Dynamic surface solver requires window core resistance for '{element.id}'")
        area = float(element.area)
        ext_surface, int_surface = cursor, cursor + 1
        cursor += 2
        core_r = float(window_core_resistances_m2k_w[element.id])
        if core_r <= 0.0:
            raise ValueError(f"Window '{element.id}' core resistance must be positive")
        h_core = area / core_r
        static_matrix[ext_surface, ext_surface] += h_core
        static_matrix[int_surface, int_surface] += h_core
        static_matrix[ext_surface, int_surface] -= h_core
        static_matrix[int_surface, ext_surface] -= h_core
        emissivity = float(emissivity_by_element.get(element.id, 0.84))
        surfaces.append(
            InteriorSurface(
                element_id=element.id,
                index=int_surface,
                area=area,
                inclination=float(getattr(element, "inclination", 90.0)),
                emissivity=emissivity,
            )
        )
        window_paths.append(
            WindowDynamicPath(
                element=element,
                exterior_surface=ext_surface,
                interior_surface=int_surface,
                boundary=t_e,
                core_h=h_core,
                wind_exposed=bool(wind_exposed_by_element.get(element.id, True)),
                roughness=roughness_by_element.get(element.id, "very_smooth"),
                emissivity=emissivity,
            )
        )

    if not surfaces:
        raise ValueError("Dynamic surface solver requires at least one internal surface")

    opaque_by_id = {element.id: element for element in exact_opaque}
    bridge_paths = _bridge_paths(bridges, zone_id, t_e, opaque_by_id)
    for bridge in bridge_paths:
        static_matrix[0, 0] += bridge.h

    total_area = float(sum(surface.area for surface in surfaces))
    default_dist = _distribution(surfaces, None)
    solar_dist = _distribution(surfaces, solar_distribution)
    internal_convective = _arr(np.zeros(n_nodes))
    internal_convective[0] = float(internal_convective_fraction)
    solar_convective = _arr(np.zeros(n_nodes))
    solar_convective[0] = float(solar_convective_fraction)
    hvac_vector = _arr(np.zeros(n_nodes))
    hvac_vector[0] = float(hvac_convective_fraction)
    operative = _arr(np.zeros(n_nodes))
    operative[0] = float(operative_air_weight)

    internal_rad = _arr(np.zeros(n_nodes))
    solar_rad = _arr(np.zeros(n_nodes))
    for distribution, solar_fraction, surface in zip(default_dist, solar_dist, surfaces, strict=True):
        internal_rad[surface.index] += (1.0 - internal_convective_fraction) * distribution
        solar_rad[surface.index] += (1.0 - solar_convective_fraction) * solar_fraction
        hvac_vector[surface.index] += (1.0 - hvac_convective_fraction) * distribution
        operative[surface.index] += (1.0 - operative_air_weight) * surface.area / total_area

    return DynamicPrepared(
        storage=storage,
        static_matrix=static_matrix,
        opaque=tuple(opaque_paths),
        windows=tuple(window_paths),
        surfaces=tuple(surfaces),
        bridges=bridge_paths,
        internal_vector_convective=internal_convective,
        internal_radiant_distribution=internal_rad,
        solar_vector_convective=solar_convective,
        solar_radiant_distribution=solar_rad,
        hvac_vector=hvac_vector,
        operative_vector=operative,
        total_surface_area=total_area,
    )


def _mrt(prepared: DynamicPrepared, state: FloatArray) -> float:
    return float(
        sum(surface.area * state[surface.index] for surface in prepared.surfaces)
        / prepared.total_surface_area
    )


def _operative(prepared: DynamicPrepared, state: FloatArray) -> float:
    return float(prepared.operative_vector @ state)


def _add_conductance(matrix: FloatArray, left: int, right: int, conductance: float) -> None:
    if conductance <= 0.0:
        return
    matrix[left, left] += conductance
    matrix[right, right] += conductance
    matrix[left, right] -= conductance
    matrix[right, left] -= conductance


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
    rhs = _arr(
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

    current_mrt = _mrt(prepared, guess)
    for surface in prepared.surfaces:
        surface_temp = float(guess[surface.index])
        kind = surface_kind_from_inclination(surface.inclination)
        h_ci = float(natural_convection_coefficient(surface_temp - float(guess[0]), kind))
        _add_conductance(matrix, 0, surface.index, surface.area * h_ci)

        h_ri = float(
            linearized_longwave_coefficient(
                surface_temp,
                current_mrt,
                emissivity=surface.emissivity,
            )
        )
        g_rad = surface.area * h_ri
        matrix[surface.index, surface.index] += g_rad
        for other in prepared.surfaces:
            matrix[surface.index, other.index] -= g_rad * other.area / prepared.total_surface_area

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
            view_sky = 0.5 * (
                1.0 + np.cos(np.deg2rad(float(path.element.inclination)))
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


def _run_cycle(
    *,
    prepared: DynamicPrepared,
    h_ve: FloatArray,
    t_supply: FloatArray,
    t_e: FloatArray,
    t_sky: FloatArray,
    wind_speed: FloatArray,
    wind_direction: FloatArray,
    phi_int: FloatArray,
    phi_sol: FloatArray,
    heat_set: FloatArray | None,
    cool_set: FloatArray | None,
    previous: FloatArray,
    nonlinear_iterations: int,
    nonlinear_tolerance_k: float,
) -> tuple[ISO52016ZoneSolution, FloatArray]:
    n = len(t_e)
    t_air = _arr(np.zeros(n))
    t_mrt = _arr(np.zeros(n))
    t_op = _arr(np.zeros(n))
    t_mass = _arr(np.zeros(n))
    t_mass_mean = _arr(np.zeros(n))
    q_h = _arr(np.zeros(n))
    q_c = _arr(np.zeros(n))
    q_tr = _arr(np.zeros(n))
    unmet_h = _arr(np.zeros(n))
    unmet_c = _arr(np.zeros(n))
    opaque_history = {path.element.id: _arr(np.empty((n, 5))) for path in prepared.opaque}
    window_history = {path.element.id: _arr(np.empty((n, 2))) for path in prepared.windows}

    state_prev = previous.copy()
    for hour in range(n):
        guess = state_prev.copy()
        current = guess
        for _ in range(max(1, nonlinear_iterations)):
            matrix, rhs = _surface_matrix_and_rhs(
                prepared=prepared,
                hour=hour,
                guess=guess,
                t_e=t_e,
                t_sky=t_sky,
                wind_speed=wind_speed,
                wind_direction=wind_direction,
                h_ve=h_ve,
                t_supply=t_supply,
                previous=state_prev,
                phi_int=phi_int,
                phi_sol=phi_sol,
            )
            free = _arr(np.linalg.solve(matrix, rhs))
            response = _arr(np.linalg.solve(matrix, prepared.hvac_vector))
            controlled_free = _operative(prepared, free)
            controlled_response = float(prepared.operative_vector @ response)
            if controlled_response <= 0.0:
                raise ValueError("Non-positive controlled-temperature response to HVAC")

            phi = 0.0
            hs = None if heat_set is None else float(heat_set[hour])
            cs = None if cool_set is None else float(cool_set[hour])
            if hs is not None and controlled_free < hs - 1e-9:
                phi = (hs - controlled_free) / controlled_response
            elif cs is not None and controlled_free > cs + 1e-9:
                phi = (cs - controlled_free) / controlled_response
            current = free if phi == 0.0 else _arr(free + phi * response)
            surface_indices = [surface.index for surface in prepared.surfaces]
            if surface_indices:
                residual = float(np.max(np.abs(current[surface_indices] - guess[surface_indices])))
            else:
                residual = 0.0
            guess = 0.5 * guess + 0.5 * current
            if residual <= nonlinear_tolerance_k:
                break

        air = float(current[0])
        mrt = _mrt(prepared, current)
        operative = _operative(prepared, current)
        t_air[hour] = air
        t_mrt[hour] = mrt
        t_op[hour] = operative
        if phi > 0.0:
            q_h[hour] = phi
        elif phi < 0.0:
            q_c[hour] = -phi
        if heat_set is not None:
            unmet_h[hour] = max(float(heat_set[hour]) - operative, 0.0)
        if cool_set is not None:
            unmet_c[hour] = max(operative - float(cool_set[hour]), 0.0)

        capacity = prepared.storage * DT
        total_capacity = float(capacity.sum())
        if total_capacity > 0.0:
            t_mass[hour] = float(capacity @ current / total_capacity)
            t_mass_mean[hour] = float(capacity @ (0.5 * (state_prev + current)) / total_capacity)
        else:
            t_mass[hour] = t_mass_mean[hour] = air

        outward = sum(
            bridge.h * (air - bridge.boundary[hour]) for bridge in prepared.bridges
        )
        for path in prepared.opaque:
            opaque_history[path.element.id][hour, :] = current[list(path.material_nodes)]
        for path in prepared.windows:
            window_history[path.element.id][hour, :] = current[
                [path.exterior_surface, path.interior_surface]
            ]
        q_tr[hour] = outward
        state_prev = current.copy()

    return (
        ISO52016ZoneSolution(
            t_air=t_air,
            t_operative=t_op,
            t_mass=t_mass,
            t_mass_mean=t_mass_mean,
            t_surface=t_mrt,
            q_heating=q_h,
            q_cooling=q_c,
            q_transmission=q_tr,
            construction_node_temperatures=opaque_history,
            used_inferred_construction=False,
            periodic_residual_k=0.0,
            t_mean_radiant=t_mrt,
            transparent_node_temperatures=window_history,
            unmet_heating_k=unmet_h,
            unmet_cooling_k=unmet_c,
        ),
        state_prev,
    )


def solve_zone_iso52016_dynamic_surfaces(
    *,
    opaque_elements: list[OpaqueElement],
    transparent_elements: Sequence[Any],
    bridges: ThermalBridgeConfig,
    zone_id: str,
    h_ve: float | FloatArray,
    t_e: FloatArray,
    phi_int: FloatArray,
    phi_sol_transparent: FloatArray,
    opaque_solar_absorbed_w_by_element: Mapping[str, FloatArray],
    t_set_heating: float | FloatArray | None,
    t_set_cooling: float | FloatArray | None,
    wind_speed_m_s: FloatArray,
    wind_direction_deg: FloatArray,
    sky_temperature_c: FloatArray,
    opaque_boundary_resistances_m2k_w: Mapping[str, tuple[float, float]],
    window_core_resistances_m2k_w: Mapping[str, float],
    air_heat_capacity_j_k: float,
    t_supply: FloatArray | None = None,
    internal_convective_fraction: float = 0.4,
    solar_convective_fraction: float = 0.1,
    hvac_convective_fraction: float = 1.0,
    operative_air_weight: float = 1.0,
    solar_radiant_distribution: Mapping[str, float] | None = None,
    wind_exposed_by_element: Mapping[str, bool] | None = None,
    roughness_by_element: Mapping[str, str] | None = None,
    emissivity_by_element: Mapping[str, float] | None = None,
    max_warmup_cycles: int = 20,
    warmup_tolerance_k: float = 0.01,
    nonlinear_iterations: int = 6,
    nonlinear_tolerance_k: float = 0.02,
) -> ISO52016ZoneSolution:
    """Solve one year with explicit dynamic surface convection/radiation.

    This path requires verified construction-node and boundary-half resistances.
    Missing physical inputs are not replaced by hidden surface-film constants.
    """
    outdoor = _arr(t_e)
    n = len(outdoor)
    if n <= 0:
        raise ValueError("t_e cannot be empty")
    ventilation = _hourly(h_ve, n, "h_ve")
    if np.any(ventilation < 0.0):
        raise ValueError("h_ve must be non-negative")
    supply = outdoor if t_supply is None else _hourly(t_supply, n, "t_supply")
    internal = _hourly(phi_int, n, "phi_int")
    solar = _hourly(phi_sol_transparent, n, "phi_sol_transparent")
    wind_speed = _hourly(wind_speed_m_s, n, "wind_speed_m_s")
    wind_direction = _hourly(wind_direction_deg, n, "wind_direction_deg")
    sky = _hourly(sky_temperature_c, n, "sky_temperature_c")
    heat_set = None if t_set_heating is None else _hourly(t_set_heating, n, "t_set_heating")
    cool_set = None if t_set_cooling is None else _hourly(t_set_cooling, n, "t_set_cooling")

    if not 0.0 <= internal_convective_fraction <= 1.0:
        raise ValueError("internal_convective_fraction must be 0..1")
    if not 0.0 <= solar_convective_fraction <= 1.0:
        raise ValueError("solar_convective_fraction must be 0..1")
    if not 0.0 <= hvac_convective_fraction <= 1.0:
        raise ValueError("hvac_convective_fraction must be 0..1")
    if not 0.0 <= operative_air_weight <= 1.0:
        raise ValueError("operative_air_weight must be 0..1")
    if air_heat_capacity_j_k < 0.0:
        raise ValueError("air_heat_capacity_j_k must be non-negative")

    prepared = _prepare_dynamic(
        opaque_elements=opaque_elements,
        transparent_elements=transparent_elements,
        bridges=bridges,
        zone_id=zone_id,
        t_e=outdoor,
        opaque_solar=opaque_solar_absorbed_w_by_element,
        air_capacity_j_k=air_heat_capacity_j_k,
        opaque_boundary_resistances_m2k_w=opaque_boundary_resistances_m2k_w,
        window_core_resistances_m2k_w=window_core_resistances_m2k_w,
        wind_exposed_by_element=wind_exposed_by_element or {},
        roughness_by_element=roughness_by_element or {},
        emissivity_by_element=emissivity_by_element or {},
        internal_convective_fraction=internal_convective_fraction,
        solar_convective_fraction=solar_convective_fraction,
        hvac_convective_fraction=hvac_convective_fraction,
        operative_air_weight=operative_air_weight,
        solar_distribution=solar_radiant_distribution,
    )

    initial_temperature = (
        float(heat_set[0])
        if heat_set is not None
        else (float(cool_set[0]) if cool_set is not None else float(outdoor.mean()))
    )
    initial = _arr(np.full(len(prepared.storage), initial_temperature))
    previous = initial
    final_solution: ISO52016ZoneSolution | None = None
    residual = float("inf")
    for _ in range(max(1, max_warmup_cycles)):
        start = previous.copy()
        final_solution, previous = _run_cycle(
            prepared=prepared,
            h_ve=ventilation,
            t_supply=supply,
            t_e=outdoor,
            t_sky=sky,
            wind_speed=wind_speed,
            wind_direction=wind_direction,
            phi_int=internal,
            phi_sol=solar,
            heat_set=heat_set,
            cool_set=cool_set,
            previous=previous,
            nonlinear_iterations=nonlinear_iterations,
            nonlinear_tolerance_k=nonlinear_tolerance_k,
        )
        residual = float(np.max(np.abs(previous - start)))
        if residual <= warmup_tolerance_k:
            break
    if final_solution is None:  # pragma: no cover
        raise RuntimeError("Dynamic surface solver did not execute")
    final_solution.periodic_residual_k = residual
    return final_solution
