"""Detailed per-construction hourly thermal-zone solver.

This solver removes the fundamental structural limitation identified by the
technical audit: opaque constructions no longer share one lumped zone mass.
Each opaque element is represented by five thermal-capacity nodes connected by
six thermal resistances (inside surface path, four construction paths and the
outside surface path). The air node is solved simultaneously with every
construction node at a one-hour time step.

For certificate-grade/hourly normative runs the nodal capacities and
resistances must be supplied explicitly for every opaque construction. A
reduced U-value + areal-capacity fallback is retained only for analytical
backwards compatibility and is exposed through ``used_inferred_construction``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast

import numpy as np
from numpy.typing import NDArray

from app.engine.envelope import adjacent_temperature
from app.schemas.models import AdjacentSpaceType, OpaqueElement, ThermalBridgeConfig

FloatArray = NDArray[np.float64]

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
    """Convert arbitrary numeric input to a float64 ndarray for typed internals."""
    return cast(FloatArray, np.asarray(value, dtype=np.float64))


def _inside_surface_resistance(element: OpaqueElement) -> float:
    """Return conventional inside surface resistance from heat-flow direction."""
    inclination = float(element.inclination)
    if inclination < 60.0:
        return 0.10
    if inclination > 120.0:
        return 0.17
    return 0.13


def _derived_resistances(element: OpaqueElement) -> FloatArray:
    total = 1.0 / float(element.u_value)
    r_si = _inside_surface_resistance(element)
    r_se = R_SE_M2K_W
    material = total - r_si - r_se
    if material <= 0.0:
        raise ValueError(
            f"Element '{element.id}' U-value is incompatible with positive "
            "surface/construction resistances; provide explicit nodal resistances"
        )
    quarter = material / 4.0
    return _float_array([r_si, quarter, quarter, quarter, quarter, r_se])


def _capacity_fractions(mass_distribution_class: str | None) -> FloatArray:
    """Reduced analytical fallback when explicit five-node capacities are absent.

    These fractions are not used in certificate mode. Their only purpose is to
    preserve analytical usability for old projects while keeping mass attached
    to individual constructions rather than a single zone-wide capacitance.
    """
    classes = {
        "internal": [0.55, 0.25, 0.12, 0.06, 0.02],
        "external": [0.02, 0.06, 0.12, 0.25, 0.55],
        "middle": [0.05, 0.15, 0.60, 0.15, 0.05],
        "internal_external": [0.40, 0.08, 0.04, 0.08, 0.40],
        "distributed": [0.20, 0.20, 0.20, 0.20, 0.20],
    }
    values = classes.get(
        mass_distribution_class or "distributed",
        classes["distributed"],
    )
    return _float_array(values)


def _construction_network(
    element: OpaqueElement,
    t_e: FloatArray,
    exterior_solar_absorbed_w: FloatArray,
    *,
    require_explicit_nodes: bool,
) -> ConstructionNetwork | None:
    if element.adjacent_space_type == AdjacentSpaceType.HEATED_ZONE:
        # The project schema already restricts such partitions to zones with
        # identical active setpoints. Net transfer is therefore zero in the
        # uncoupled-zone calculation.
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
    h_bridge = sum(
        float(bridge.psi_value) * float(bridge.length)
        for bridge in bridges.linear_bridges
        if bridge.zone_id == zone_id
    )
    h_bridge += sum(
        float(bridge.chi_value) * int(bridge.count)
        for bridge in bridges.point_bridges
        if bridge.zone_id == zone_id
    )
    return float(h_bridge)


def _as_hourly(value: float | FloatArray, n: int, name: str) -> FloatArray:
    array = _float_array(value)
    if array.ndim == 0:
        array = cast(FloatArray, np.full(n, float(array), dtype=np.float64))
    if array.shape != (n,):
        raise ValueError(f"{name} must be scalar or contain one value per hour")
    if not np.isfinite(array).all():
        raise ValueError(f"{name} must contain finite values")
    return array


def _solve_cycle(
    *,
    constructions: list[ConstructionNetwork],
    transparent_elements: Sequence[Any],
    bridges: ThermalBridgeConfig,
    zone_id: str,
    h_ve: FloatArray,
    t_e: FloatArray,
    t_supply: FloatArray,
    phi_int: FloatArray,
    phi_sol_transparent: FloatArray,
    t_set_heating: float | None,
    t_set_cooling: float | None,
    previous_nodes: FloatArray,
) -> tuple[ISO52016ZoneSolution, FloatArray]:
    n = len(t_e)
    construction_count = len(constructions)
    node_count = 1 + 5 * construction_count
    if previous_nodes.shape != (5 * construction_count,):
        raise ValueError("previous construction state has invalid shape")

    h_windows = float(
        sum(float(element.area) * float(element.u_value) for element in transparent_elements)
    )
    h_bridge = _bridge_conductance(bridges, zone_id)
    interior_areas: FloatArray = _float_array(
        [float(construction.element.area) for construction in constructions]
    )
    total_interior_area = float(interior_areas.sum())

    t_air: FloatArray = cast(FloatArray, np.empty(n, dtype=np.float64))
    t_surface: FloatArray = cast(FloatArray, np.empty(n, dtype=np.float64))
    t_operative: FloatArray = cast(FloatArray, np.empty(n, dtype=np.float64))
    t_mass: FloatArray = cast(FloatArray, np.empty(n, dtype=np.float64))
    t_mass_mean: FloatArray = cast(FloatArray, np.empty(n, dtype=np.float64))
    q_h: FloatArray = cast(FloatArray, np.zeros(n, dtype=np.float64))
    q_c: FloatArray = cast(FloatArray, np.zeros(n, dtype=np.float64))
    q_transmission: FloatArray = cast(FloatArray, np.zeros(n, dtype=np.float64))
    node_history: dict[str, FloatArray] = {
        construction.element.id: cast(
            FloatArray,
            np.empty((n, 5), dtype=np.float64),
        )
        for construction in constructions
    }

    capacities_all: FloatArray = (
        cast(
            FloatArray,
            np.concatenate([construction.capacities_j_k for construction in constructions]),
        )
        if constructions
        else cast(FloatArray, np.empty(0, dtype=np.float64))
    )
    capacity_sum = float(capacities_all.sum())
    previous: FloatArray = previous_nodes.copy()

    for hour in range(n):
        matrix: FloatArray = cast(
            FloatArray,
            np.zeros((node_count, node_count), dtype=np.float64),
        )
        rhs: FloatArray = cast(FloatArray, np.zeros(node_count, dtype=np.float64))

        h_si_total = 0.0
        for i, construction in enumerate(constructions):
            base = 1 + 5 * i
            area = float(construction.element.area)
            h_segments: FloatArray = _float_array(
                area / construction.resistances_m2k_w
            )
            h_si = float(h_segments[0])
            h_si_total += h_si
            matrix[0, base] -= h_si

            for node in range(5):
                row = base + node
                capacity = float(construction.capacities_j_k[node])
                storage = capacity / SECONDS_PER_HOUR
                h_left = float(h_segments[node])
                h_right = float(h_segments[node + 1])
                matrix[row, row] += storage + h_left + h_right
                rhs[row] += storage * previous[5 * i + node]

                if node == 0:
                    matrix[row, 0] -= h_left
                else:
                    matrix[row, row - 1] -= h_left
                if node == 4:
                    rhs[row] += h_right * construction.boundary_temperature_c[hour]
                    rhs[row] += construction.exterior_solar_absorbed_w[hour]
                else:
                    matrix[row, row + 1] -= h_right

        matrix[0, 0] = h_ve[hour] + h_windows + h_bridge + h_si_total
        rhs[0] = (
            h_ve[hour] * t_supply[hour]
            + (h_windows + h_bridge) * t_e[hour]
            + 0.5 * phi_int[hour]
        )

        radiant_gain = 0.5 * phi_int[hour] + phi_sol_transparent[hour]
        if constructions and total_interior_area > 0.0:
            for i, area in enumerate(interior_areas):
                rhs[1 + 5 * i] += radiant_gain * area / total_interior_area
        else:
            rhs[0] += radiant_gain

        free: FloatArray = _float_array(np.linalg.solve(matrix, rhs))
        unit_rhs: FloatArray = cast(
            FloatArray,
            np.zeros(node_count, dtype=np.float64),
        )
        unit_rhs[0] = 1.0
        unit: FloatArray = _float_array(np.linalg.solve(matrix, unit_rhs))
        response = float(unit[0])
        if response <= 0.0:
            raise ValueError("Hourly construction network is insensitive to HVAC input")

        phi_hc = 0.0
        eps = 1e-9
        if t_set_heating is not None and free[0] < t_set_heating - eps:
            phi_hc = (t_set_heating - free[0]) / response
            q_h[hour] = phi_hc
        elif t_set_cooling is not None and free[0] > t_set_cooling + eps:
            phi_hc = (t_set_cooling - free[0]) / response
            q_c[hour] = -phi_hc
        current: FloatArray = (
            free if phi_hc == 0.0 else _float_array(free + phi_hc * unit)
        )

        t_air[hour] = current[0]
        if constructions:
            surface_value = float(
                sum(
                    interior_areas[i] * current[1 + 5 * i]
                    for i in range(construction_count)
                )
                / total_interior_area
            )
        else:
            surface_value = float(current[0])
        t_surface[hour] = surface_value
        t_operative[hour] = 0.3 * current[0] + 0.7 * surface_value

        current_nodes: FloatArray = _float_array(current[1:])
        if capacity_sum > 0.0:
            t_mass[hour] = float(np.dot(current_nodes, capacities_all) / capacity_sum)
            t_mass_mean[hour] = float(
                np.dot(0.5 * (previous + current_nodes), capacities_all) / capacity_sum
            )
        else:
            t_mass[hour] = float(current[0])
            t_mass_mean[hour] = float(current[0])

        outward = (h_windows + h_bridge) * (current[0] - t_e[hour])
        for i, construction in enumerate(constructions):
            area = float(construction.element.area)
            h_ext = area / float(construction.resistances_m2k_w[5])
            exterior_node = current[1 + 5 * i + 4]
            outward += h_ext * (
                exterior_node - construction.boundary_temperature_c[hour]
            )
            node_history[construction.element.id][hour, :] = current[
                1 + 5 * i : 1 + 5 * i + 5
            ]
        q_transmission[hour] = outward
        previous = current_nodes.copy()

    solution = ISO52016ZoneSolution(
        t_air=t_air,
        t_operative=t_operative,
        t_mass=t_mass,
        t_mass_mean=t_mass_mean,
        t_surface=t_surface,
        q_heating=q_h,
        q_cooling=q_c,
        q_transmission=q_transmission,
        construction_node_temperatures=node_history,
        used_inferred_construction=any(item.inferred for item in constructions),
        periodic_residual_k=0.0,
    )
    return solution, previous


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
    require_explicit_construction_nodes: bool = False,
    max_warmup_cycles: int = 20,
    warmup_tolerance_k: float = 0.01,
) -> ISO52016ZoneSolution:
    """Solve one thermal zone with separate five-node opaque constructions."""
    outdoor: FloatArray = _float_array(t_e)
    n = len(outdoor)
    if n == 0:
        raise ValueError("Hourly solver requires at least one hour")
    supply: FloatArray = (
        outdoor if t_supply is None else _as_hourly(t_supply, n, "t_supply")
    )
    ventilation: FloatArray = _as_hourly(h_ve, n, "h_ve")
    if np.any(ventilation < 0.0):
        raise ValueError("h_ve must be non-negative")
    internal: FloatArray = _as_hourly(phi_int, n, "phi_int")
    transparent_solar: FloatArray = _as_hourly(
        phi_sol_transparent,
        n,
        "phi_sol_transparent",
    )

    constructions: list[ConstructionNetwork] = []
    for element in opaque_elements:
        solar: FloatArray = opaque_solar_absorbed_w_by_element.get(
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

    initial_temperature = float(
        t_set_heating
        if t_set_heating is not None
        else (t_set_cooling if t_set_cooling is not None else outdoor[0])
    )
    previous: FloatArray = cast(
        FloatArray,
        np.full(5 * len(constructions), initial_temperature, dtype=np.float64),
    )
    cycles = max_warmup_cycles if n == 8760 else 1
    solution: ISO52016ZoneSolution | None = None
    residual = 0.0
    for _ in range(cycles):
        start: FloatArray = previous.copy()
        solution, previous = _solve_cycle(
            constructions=constructions,
            transparent_elements=transparent_elements,
            bridges=bridges,
            zone_id=zone_id,
            h_ve=ventilation,
            t_e=outdoor,
            t_supply=supply,
            phi_int=internal,
            phi_sol_transparent=transparent_solar,
            t_set_heating=t_set_heating,
            t_set_cooling=t_set_cooling,
            previous_nodes=start,
        )
        residual = float(np.max(np.abs(previous - start))) if previous.size else 0.0
        if cycles == 1 or residual <= warmup_tolerance_k:
            if cycles > 1:
                solution, previous = _solve_cycle(
                    constructions=constructions,
                    transparent_elements=transparent_elements,
                    bridges=bridges,
                    zone_id=zone_id,
                    h_ve=ventilation,
                    t_e=outdoor,
                    t_supply=supply,
                    phi_int=internal,
                    phi_sol_transparent=transparent_solar,
                    t_set_heating=t_set_heating,
                    t_set_cooling=t_set_cooling,
                    previous_nodes=previous,
                )
            break
    if solution is None:  # pragma: no cover
        raise RuntimeError("Hourly construction solver did not produce a solution")
    solution.periodic_residual_k = residual
    return solution
