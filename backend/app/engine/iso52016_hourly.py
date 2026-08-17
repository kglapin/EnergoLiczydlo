"""Detailed per-construction hourly thermal-zone solver.

Each opaque construction owns five thermal-capacity nodes connected by six
thermal-resistance paths. The air node and every construction node are solved
simultaneously at a one-hour step. Constant matrix terms are precomputed once
per annual cycle and matrix inverses are cached by ventilation conductance, so
performance does not depend on rebuilding/solving the same matrix twice for
every hour.

Certificate-grade runs require explicit nodal capacities and resistances.
Reduced U-value + areal-capacity inputs remain an analytical fallback only.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, TypeAlias, cast

import numpy as np
from numpy.typing import NDArray

from app.engine.envelope import adjacent_temperature
from app.schemas.models import AdjacentSpaceType, OpaqueElement, ThermalBridgeConfig

FloatArray: TypeAlias = NDArray[np.float64]

SECONDS_PER_HOUR = 3600.0
DEFAULT_AREAL_HEAT_CAPACITY_KJ_M2K = 165.0
R_SE_M2K_W = 0.04


@dataclass(frozen=True)
class ConstructionNetwork:
    element: OpaqueElement
    resistances_m2k_w: FloatArray
    capacities_j_k: FloatArray
    boundary_temperature_c: FloatArray
    exterior_solar_absorbed_w: FloatArray
    inferred: bool


@dataclass(frozen=True)
class _PreparedNetwork:
    matrix_base: FloatArray
    constructions: tuple[ConstructionNetwork, ...]
    h_segments: tuple[FloatArray, ...]
    interior_areas: FloatArray
    total_interior_area: float
    capacities_all: FloatArray
    storage_coefficients: FloatArray
    capacity_sum: float
    h_windows: float
    h_bridge: float


@dataclass
class ISO52016ZoneSolution:
    t_air: FloatArray
    t_operative: FloatArray
    t_mass: FloatArray
    t_mass_mean: FloatArray
    t_surface: FloatArray
    q_heating: FloatArray
    q_cooling: FloatArray
    q_transmission: FloatArray
    construction_node_temperatures: dict[str, FloatArray]
    used_inferred_construction: bool
    periodic_residual_k: float


def _float_array(value: Any) -> FloatArray:
    return cast(FloatArray, np.asarray(value, dtype=np.float64))


def _inside_surface_resistance(element: OpaqueElement) -> float:
    inclination = float(element.inclination)
    if inclination < 60.0:
        return 0.10
    if inclination > 120.0:
        return 0.17
    return 0.13


def _derived_resistances(element: OpaqueElement) -> FloatArray:
    total = 1.0 / float(element.u_value)
    r_si = _inside_surface_resistance(element)
    material = total - r_si - R_SE_M2K_W
    if material <= 0.0:
        raise ValueError(
            f"Element '{element.id}' U-value is incompatible with positive "
            "surface/construction resistances; provide explicit nodal resistances"
        )
    quarter = material / 4.0
    return _float_array([r_si, quarter, quarter, quarter, quarter, R_SE_M2K_W])


def _capacity_fractions(mass_distribution_class: str | None) -> FloatArray:
    classes = {
        "internal": [0.55, 0.25, 0.12, 0.06, 0.02],
        "external": [0.02, 0.06, 0.12, 0.25, 0.55],
        "middle": [0.05, 0.15, 0.60, 0.15, 0.05],
        "internal_external": [0.40, 0.08, 0.04, 0.08, 0.40],
        "distributed": [0.20, 0.20, 0.20, 0.20, 0.20],
    }
    return _float_array(
        classes.get(
            mass_distribution_class or "distributed",
            classes["distributed"],
        )
    )


def _construction_network(
    element: OpaqueElement,
    t_e: FloatArray,
    exterior_solar_absorbed_w: FloatArray,
    *,
    require_explicit_nodes: bool,
) -> ConstructionNetwork | None:
    if element.adjacent_space_type == AdjacentSpaceType.HEATED_ZONE:
        return None

    explicit_capacities = element.thermal_node_capacities_kj_m2k
    explicit_resistances = element.thermal_node_resistances_m2k_w
    explicit = explicit_capacities is not None and explicit_resistances is not None
    if require_explicit_nodes and not explicit:
        raise ValueError(
            "Detailed ISO 52016 certificate mode requires explicit five-node "
            f"construction data for opaque element '{element.id}'"
        )

    if explicit:
        resistances = _float_array(explicit_resistances)
        capacities_areal = _float_array(explicit_capacities)
        inferred = False
    else:
        resistances = _derived_resistances(element)
        areal_capacity = float(
            element.areal_heat_capacity
            if element.areal_heat_capacity is not None
            else DEFAULT_AREAL_HEAT_CAPACITY_KJ_M2K
        )
        capacities_areal = _float_array(
            areal_capacity * _capacity_fractions(element.mass_distribution_class)
        )
        inferred = True

    capacities = _float_array(capacities_areal * float(element.area) * 1000.0)
    boundary = _float_array(adjacent_temperature(element, t_e))
    solar = _float_array(exterior_solar_absorbed_w)
    if solar.shape != t_e.shape:
        raise ValueError(
            f"Exterior solar absorption for '{element.id}' must match climate length"
        )
    return ConstructionNetwork(
        element=element,
        resistances_m2k_w=resistances,
        capacities_j_k=capacities,
        boundary_temperature_c=boundary,
        exterior_solar_absorbed_w=solar,
        inferred=inferred,
    )


def _bridge_conductance(bridges: ThermalBridgeConfig, zone_id: str) -> float:
    linear = sum(
        float(bridge.psi_value) * float(bridge.length)
        for bridge in bridges.linear_bridges
        if bridge.zone_id == zone_id
    )
    point = sum(
        float(bridge.chi_value) * int(bridge.count)
        for bridge in bridges.point_bridges
        if bridge.zone_id == zone_id
    )
    return float(linear + point)


def _as_hourly(value: float | FloatArray, n: int, name: str) -> FloatArray:
    array = _float_array(value)
    if array.ndim == 0:
        array = cast(FloatArray, np.full(n, float(array), dtype=np.float64))
    if array.shape != (n,):
        raise ValueError(f"{name} must be scalar or contain one value per hour")
    if not np.isfinite(array).all():
        raise ValueError(f"{name} must contain finite values")
    return array


def _prepare_network(
    constructions: list[ConstructionNetwork],
    transparent_elements: Sequence[Any],
    bridges: ThermalBridgeConfig,
    zone_id: str,
) -> _PreparedNetwork:
    count = len(constructions)
    node_count = 1 + 5 * count
    matrix = cast(FloatArray, np.zeros((node_count, node_count), dtype=np.float64))
    h_windows = float(
        sum(float(element.area) * float(element.u_value) for element in transparent_elements)
    )
    h_bridge = _bridge_conductance(bridges, zone_id)
    h_segments: list[FloatArray] = []
    h_si_total = 0.0

    for i, construction in enumerate(constructions):
        base = 1 + 5 * i
        area = float(construction.element.area)
        segments = _float_array(area / construction.resistances_m2k_w)
        h_segments.append(segments)
        h_si = float(segments[0])
        h_si_total += h_si
        matrix[0, base] -= h_si

        for node in range(5):
            row = base + node
            storage = float(construction.capacities_j_k[node]) / SECONDS_PER_HOUR
            h_left = float(segments[node])
            h_right = float(segments[node + 1])
            matrix[row, row] += storage + h_left + h_right
            if node == 0:
                matrix[row, 0] -= h_left
            else:
                matrix[row, row - 1] -= h_left
            if node < 4:
                matrix[row, row + 1] -= h_right

    matrix[0, 0] = h_windows + h_bridge + h_si_total
    areas = _float_array([float(item.element.area) for item in constructions])
    capacities_all = (
        _float_array(np.concatenate([item.capacities_j_k for item in constructions]))
        if constructions
        else cast(FloatArray, np.empty(0, dtype=np.float64))
    )
    return _PreparedNetwork(
        matrix_base=matrix,
        constructions=tuple(constructions),
        h_segments=tuple(h_segments),
        interior_areas=areas,
        total_interior_area=float(areas.sum()),
        capacities_all=capacities_all,
        storage_coefficients=_float_array(capacities_all / SECONDS_PER_HOUR),
        capacity_sum=float(capacities_all.sum()),
        h_windows=h_windows,
        h_bridge=h_bridge,
    )


def _inverse_for_hve(
    prepared: _PreparedNetwork,
    h_ve: float,
    cache: dict[float, tuple[FloatArray, FloatArray]],
) -> tuple[FloatArray, FloatArray]:
    key = float(h_ve)
    cached = cache.get(key)
    if cached is not None:
        return cached
    matrix = prepared.matrix_base.copy()
    matrix[0, 0] += key
    if matrix.shape == (1, 1) and matrix[0, 0] <= 0.0:
        raise ValueError("Hourly zone has no thermal path or air capacitance")
    inverse = _float_array(np.linalg.inv(matrix))
    unit = _float_array(inverse[:, 0])
    if float(unit[0]) <= 0.0:
        raise ValueError("Hourly construction network is insensitive to HVAC input")
    result = (inverse, unit)
    cache[key] = result
    return result


def _solve_cycle(
    *,
    prepared: _PreparedNetwork,
    h_ve: FloatArray,
    t_e: FloatArray,
    t_supply: FloatArray,
    phi_int: FloatArray,
    phi_sol_transparent: FloatArray,
    internal_convective_fraction: float,
    t_set_heating: float | None,
    t_set_cooling: float | None,
    previous_nodes: FloatArray,
) -> tuple[ISO52016ZoneSolution, FloatArray]:
    n = len(t_e)
    count = len(prepared.constructions)
    if previous_nodes.shape != (5 * count,):
        raise ValueError("previous construction state has invalid shape")

    t_air = cast(FloatArray, np.empty(n, dtype=np.float64))
    t_surface = cast(FloatArray, np.empty(n, dtype=np.float64))
    t_operative = cast(FloatArray, np.empty(n, dtype=np.float64))
    t_mass = cast(FloatArray, np.empty(n, dtype=np.float64))
    t_mass_mean = cast(FloatArray, np.empty(n, dtype=np.float64))
    q_h = cast(FloatArray, np.zeros(n, dtype=np.float64))
    q_c = cast(FloatArray, np.zeros(n, dtype=np.float64))
    q_transmission = cast(FloatArray, np.zeros(n, dtype=np.float64))
    node_history = {
        item.element.id: cast(FloatArray, np.empty((n, 5), dtype=np.float64))
        for item in prepared.constructions
    }
    previous = previous_nodes.copy()
    inverse_cache: dict[float, tuple[FloatArray, FloatArray]] = {}

    for hour in range(n):
        inverse, unit = _inverse_for_hve(prepared, float(h_ve[hour]), inverse_cache)
        rhs = cast(FloatArray, np.zeros(inverse.shape[0], dtype=np.float64))
        rhs[0] = (
            h_ve[hour] * t_supply[hour]
            + (prepared.h_windows + prepared.h_bridge) * t_e[hour]
            + internal_convective_fraction * phi_int[hour]
        )
        if previous.size:
            rhs[1:] = prepared.storage_coefficients * previous

        radiant = (
            (1.0 - internal_convective_fraction) * phi_int[hour]
            + phi_sol_transparent[hour]
        )
        if count and prepared.total_interior_area > 0.0:
            for i, construction in enumerate(prepared.constructions):
                rhs[1 + 5 * i] += (
                    radiant
                    * prepared.interior_areas[i]
                    / prepared.total_interior_area
                )
                rhs[1 + 5 * i + 4] += (
                    prepared.h_segments[i][5]
                    * construction.boundary_temperature_c[hour]
                    + construction.exterior_solar_absorbed_w[hour]
                )
        else:
            rhs[0] += radiant

        free = _float_array(inverse @ rhs)
        response = float(unit[0])
        phi_hc = 0.0
        if t_set_heating is not None and free[0] < t_set_heating - 1e-9:
            phi_hc = (t_set_heating - free[0]) / response
            q_h[hour] = phi_hc
        elif t_set_cooling is not None and free[0] > t_set_cooling + 1e-9:
            phi_hc = (t_set_cooling - free[0]) / response
            q_c[hour] = -phi_hc
        current = free if phi_hc == 0.0 else _float_array(free + phi_hc * unit)

        t_air[hour] = current[0]
        if count:
            surface = float(
                sum(
                    prepared.interior_areas[i] * current[1 + 5 * i]
                    for i in range(count)
                )
                / prepared.total_interior_area
            )
        else:
            surface = float(current[0])
        t_surface[hour] = surface
        t_operative[hour] = 0.3 * current[0] + 0.7 * surface

        nodes = _float_array(current[1:])
        if prepared.capacity_sum > 0.0:
            t_mass[hour] = float(
                np.dot(nodes, prepared.capacities_all) / prepared.capacity_sum
            )
            t_mass_mean[hour] = float(
                np.dot(0.5 * (previous + nodes), prepared.capacities_all)
                / prepared.capacity_sum
            )
        else:
            t_mass[hour] = float(current[0])
            t_mass_mean[hour] = float(current[0])

        outward = (prepared.h_windows + prepared.h_bridge) * (current[0] - t_e[hour])
        for i, construction in enumerate(prepared.constructions):
            exterior_node = current[1 + 5 * i + 4]
            outward += prepared.h_segments[i][5] * (
                exterior_node - construction.boundary_temperature_c[hour]
            )
            node_history[construction.element.id][hour, :] = current[
                1 + 5 * i : 1 + 5 * i + 5
            ]
        q_transmission[hour] = outward
        previous = nodes.copy()

    return (
        ISO52016ZoneSolution(
            t_air=t_air,
            t_operative=t_operative,
            t_mass=t_mass,
            t_mass_mean=t_mass_mean,
            t_surface=t_surface,
            q_heating=q_h,
            q_cooling=q_c,
            q_transmission=q_transmission,
            construction_node_temperatures=node_history,
            used_inferred_construction=any(
                item.inferred for item in prepared.constructions
            ),
            periodic_residual_k=0.0,
        ),
        previous,
    )


def solve_zone_iso52016(
    *,
    opaque_elements: list[OpaqueElement],
    transparent_elements: Sequence[Any],
    bridges: ThermalBridgeConfig,
    zone_id: str,
    h_ve: float | FloatArray,
    t_e: FloatArray,
    phi_int: FloatArray,
    phi_sol_transparent: FloatArray,
    opaque_solar_absorbed_w_by_element: dict[str, FloatArray],
    t_set_heating: float | None,
    t_set_cooling: float | None,
    t_supply: FloatArray | None = None,
    internal_convective_fraction: float = 0.5,
    require_explicit_construction_nodes: bool = False,
    max_warmup_cycles: int = 20,
    warmup_tolerance_k: float = 0.01,
) -> ISO52016ZoneSolution:
    outdoor = _float_array(t_e)
    n = len(outdoor)
    if n == 0:
        raise ValueError("Hourly solver requires at least one hour")
    if not np.isfinite(internal_convective_fraction) or not (
        0.0 <= internal_convective_fraction <= 1.0
    ):
        raise ValueError("internal_convective_fraction must be between 0 and 1")
    supply = outdoor if t_supply is None else _as_hourly(t_supply, n, "t_supply")
    ventilation = _as_hourly(h_ve, n, "h_ve")
    if np.any(ventilation < 0.0):
        raise ValueError("h_ve must be non-negative")
    internal = _as_hourly(phi_int, n, "phi_int")
    transparent_solar = _as_hourly(
        phi_sol_transparent,
        n,
        "phi_sol_transparent",
    )

    constructions: list[ConstructionNetwork] = []
    for element in opaque_elements:
        solar = opaque_solar_absorbed_w_by_element.get(
            element.id,
            cast(FloatArray, np.zeros(n, dtype=np.float64)),
        )
        construction = _construction_network(
            element,
            outdoor,
            _float_array(solar),
            require_explicit_nodes=require_explicit_construction_nodes,
        )
        if construction is not None:
            constructions.append(construction)

    prepared = _prepare_network(
        constructions,
        transparent_elements,
        bridges,
        zone_id,
    )
    initial_temperature = float(
        t_set_heating
        if t_set_heating is not None
        else (t_set_cooling if t_set_cooling is not None else outdoor[0])
    )
    previous = cast(
        FloatArray,
        np.full(5 * len(constructions), initial_temperature, dtype=np.float64),
    )
    cycles = max_warmup_cycles if n == 8760 else 1
    solution: ISO52016ZoneSolution | None = None
    residual = 0.0

    for _ in range(cycles):
        start = previous.copy()
        solution, previous = _solve_cycle(
            prepared=prepared,
            h_ve=ventilation,
            t_e=outdoor,
            t_supply=supply,
            phi_int=internal,
            phi_sol_transparent=transparent_solar,
            internal_convective_fraction=internal_convective_fraction,
            t_set_heating=t_set_heating,
            t_set_cooling=t_set_cooling,
            previous_nodes=start,
        )
        residual = float(np.max(np.abs(previous - start))) if previous.size else 0.0
        if cycles == 1 or residual <= warmup_tolerance_k:
            if cycles > 1:
                solution, _ = _solve_cycle(
                    prepared=prepared,
                    h_ve=ventilation,
                    t_e=outdoor,
                    t_supply=supply,
                    phi_int=internal,
                    phi_sol_transparent=transparent_solar,
                    internal_convective_fraction=internal_convective_fraction,
                    t_set_heating=t_set_heating,
                    t_set_cooling=t_set_cooling,
                    previous_nodes=previous,
                )
            break

    if solution is None:  # pragma: no cover
        raise RuntimeError("Hourly construction solver did not produce a solution")
    if n == 8760 and residual > warmup_tolerance_k:
        raise RuntimeError(
            "Hourly construction solver did not reach periodic state: "
            f"residual={residual:.6f} K after {max_warmup_cycles} cycles"
        )
    solution.periodic_residual_k = residual
    return solution
