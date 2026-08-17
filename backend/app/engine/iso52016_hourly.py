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

from dataclasses import dataclass

import numpy as np

from app.engine.envelope import adjacent_temperature
from app.schemas.models import AdjacentSpaceType, OpaqueElement, ThermalBridgeConfig

SECONDS_PER_HOUR = 3600.0
DEFAULT_AREAL_HEAT_CAPACITY_KJ_M2K = 165.0
R_SE_M2K_W = 0.04


@dataclass(frozen=True)
class ConstructionNetwork:
    element: OpaqueElement
    resistances_m2k_w: np.ndarray
    capacities_j_k: np.ndarray
    boundary_temperature_c: np.ndarray
    exterior_solar_absorbed_w: np.ndarray
    inferred: bool


@dataclass
class ISO52016ZoneSolution:
    t_air: np.ndarray
    t_operative: np.ndarray
    t_mass: np.ndarray
    t_mass_mean: np.ndarray
    t_surface: np.ndarray
    q_heating: np.ndarray
    q_cooling: np.ndarray
    q_transmission: np.ndarray
    construction_node_temperatures: dict[str, np.ndarray]
    used_inferred_construction: bool
    periodic_residual_k: float


def _inside_surface_resistance(element: OpaqueElement) -> float:
    """Return conventional inside surface resistance from heat-flow direction."""
    inclination = float(element.inclination)
    if inclination < 60.0:
        return 0.10
    if inclination > 120.0:
        return 0.17
    return 0.13


def _derived_resistances(element: OpaqueElement) -> np.ndarray:
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
    return np.asarray([r_si, quarter, quarter, quarter, quarter, r_se], dtype=float)


def _capacity_fractions(mass_distribution_class: str | None) -> np.ndarray:
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
    return np.asarray(classes.get(mass_distribution_class or "distributed", classes["distributed"]))


def _construction_network(
    element: OpaqueElement,
    t_e: np.ndarray,
    exterior_solar_absorbed_w: np.ndarray,
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
        resistances = np.asarray(explicit_resistances, dtype=float)
        capacities_areal = np.asarray(explicit_capacities, dtype=float)
        inferred = False
    else:
        resistances = _derived_resistances(element)
        areal_capacity = float(
            element.areal_heat_capacity
            if element.areal_heat_capacity is not None
            else DEFAULT_AREAL_HEAT_CAPACITY_KJ_M2K
        )
        capacities_areal = areal_capacity * _capacity_fractions(
            element.mass_distribution_class
        )
        inferred = True

    capacities = capacities_areal * float(element.area) * 1000.0
    boundary = adjacent_temperature(element, t_e)
    solar = np.asarray(exterior_solar_absorbed_w, dtype=float)
    if solar.shape != t_e.shape:
        raise ValueError(
            f"Exterior solar absorption for '{element.id}' must match climate length"
        )
    return ConstructionNetwork(
        element=element,
        resistances_m2k_w=resistances,
        capacities_j_k=capacities,
        boundary_temperature_c=np.asarray(boundary, dtype=float),
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


def _as_hourly(value: float | np.ndarray, n: int, name: str) -> np.ndarray:
    array = np.asarray(value, dtype=float)
    if array.ndim == 0:
        array = np.full(n, float(array), dtype=float)
    if array.shape != (n,):
        raise ValueError(f"{name} must be scalar or contain one value per hour")
    if not np.isfinite(array).all():
        raise ValueError(f"{name} must contain finite values")
    return array


def _solve_cycle(
    *,
    constructions: list[ConstructionNetwork],
    transparent_elements,
    bridges: ThermalBridgeConfig,
    zone_id: str,
    h_ve: np.ndarray,
    t_e: np.ndarray,
    t_supply: np.ndarray,
    phi_int: np.ndarray,
    phi_sol_transparent: np.ndarray,
    t_set_heating: float | None,
    t_set_cooling: float | None,
    previous_nodes: np.ndarray,
):
    n = len(t_e)
    construction_count = len(constructions)
    node_count = 1 + 5 * construction_count
    if previous_nodes.shape != (5 * construction_count,):
        raise ValueError("previous construction state has invalid shape")

    h_windows = float(
        sum(float(element.area) * float(element.u_value) for element in transparent_elements)
    )
    h_bridge = _bridge_conductance(bridges, zone_id)
    interior_areas = np.asarray(
        [float(construction.element.area) for construction in constructions],
        dtype=float,
    )
    total_interior_area = float(interior_areas.sum())

    t_air = np.empty(n, dtype=float)
    t_surface = np.empty(n, dtype=float)
    t_operative = np.empty(n, dtype=float)
    t_mass = np.empty(n, dtype=float)
    t_mass_mean = np.empty(n, dtype=float)
    q_h = np.zeros(n, dtype=float)
    q_c = np.zeros(n, dtype=float)
    q_transmission = np.zeros(n, dtype=float)
    node_history = {
        construction.element.id: np.empty((n, 5), dtype=float)
        for construction in constructions
    }

    capacities_all = np.concatenate(
        [construction.capacities_j_k for construction in constructions]
    ) if constructions else np.empty(0, dtype=float)
    capacity_sum = float(capacities_all.sum())
    previous = previous_nodes.copy()

    for hour in range(n):
        matrix = np.zeros((node_count, node_count), dtype=float)
        rhs = np.zeros(node_count, dtype=float)

        h_si_total = 0.0
        for i, construction in enumerate(constructions):
            base = 1 + 5 * i
            area = float(construction.element.area)
            h_segments = area / construction.resistances_m2k_w
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

        free = np.linalg.solve(matrix, rhs)
        unit_rhs = np.zeros(node_count, dtype=float)
        unit_rhs[0] = 1.0
        unit = np.linalg.solve(matrix, unit_rhs)
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
        current = free if phi_hc == 0.0 else free + phi_hc * unit

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

        current_nodes = current[1:]
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
    transparent_elements,
    bridges: ThermalBridgeConfig,
    zone_id: str,
    h_ve: float | np.ndarray,
    t_e: np.ndarray,
    phi_int: np.ndarray,
    phi_sol_transparent: np.ndarray,
    opaque_solar_absorbed_w_by_element: dict[str, np.ndarray],
    t_set_heating: float | None,
    t_set_cooling: float | None,
    t_supply: np.ndarray | None = None,
    require_explicit_construction_nodes: bool = False,
    max_warmup_cycles: int = 20,
    warmup_tolerance_k: float = 0.01,
) -> ISO52016ZoneSolution:
    """Solve one thermal zone with separate five-node opaque constructions."""
    outdoor = np.asarray(t_e, dtype=float)
    n = len(outdoor)
    if n == 0:
        raise ValueError("Hourly solver requires at least one hour")
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
            np.zeros(n, dtype=float),
        )
        construction = _construction_network(
            element,
            outdoor,
            np.asarray(solar, dtype=float),
            require_explicit_nodes=require_explicit_construction_nodes,
        )
        if construction is not None:
            constructions.append(construction)

    initial_temperature = float(
        t_set_heating
        if t_set_heating is not None
        else (t_set_cooling if t_set_cooling is not None else outdoor[0])
    )
    previous = np.full(5 * len(constructions), initial_temperature, dtype=float)
    cycles = max_warmup_cycles if n == 8760 else 1
    solution: ISO52016ZoneSolution | None = None
    residual = 0.0
    for _ in range(cycles):
        start = previous.copy()
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
