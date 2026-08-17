"""PN-EN ISO 52016-1 hourly sensible thermal-zone solver.

The state follows clause 6.5: a dynamic indoor-air/furniture node, five nodes
per opaque element (ordered exterior -> interior) and two zero-capacity nodes
per transparent element. Surface convection and long-wave radiation are kept
separate, HVAC is controlled on operative temperature and annual runs are
initialized to a periodic state.

Inputs delegated by ISO 52016-1 to other EPB standards are explicit in strict
mode. The compatibility fallback remains available for old project files but
is marked as inferred and must not be presented as certificate-grade output.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypeAlias, cast

import numpy as np
from numpy.typing import NDArray

from app.engine.envelope import adjacent_temperature
from app.schemas.models import AdjacentSpaceType, OpaqueElement, ThermalBridgeConfig

FloatArray: TypeAlias = NDArray[np.float64]
DT = 3600.0
DEFAULT_AIR_FURNITURE_CAPACITY_KJ_M2K = 10.0
DEFAULT_AREAL_CAPACITY_KJ_M2K = 165.0


@dataclass(frozen=True)
class Film:
    h_ci: float
    h_ri: float
    h_ce: float
    h_re: float
    inferred: bool = False


@dataclass(frozen=True)
class OpaquePath:
    element: OpaqueElement
    indices: tuple[int, int, int, int, int]
    boundary: FloatArray
    h_boundary: float
    solar_w: FloatArray
    sky_w: FloatArray
    capacities_j_k: FloatArray
    inferred: bool


@dataclass(frozen=True)
class WindowPath:
    element: Any
    indices: tuple[int, int]
    boundary: FloatArray
    h_boundary: float
    inferred: bool


@dataclass(frozen=True)
class Surface:
    element_id: str
    index: int
    area: float
    h_ri: float


@dataclass(frozen=True)
class BridgePath:
    h: float
    boundary: FloatArray


@dataclass(frozen=True)
class Prepared:
    matrix: FloatArray
    storage: FloatArray
    capacity_mask: NDArray[np.bool_]
    opaque: tuple[OpaquePath, ...]
    windows: tuple[WindowPath, ...]
    surfaces: tuple[Surface, ...]
    bridges: tuple[BridgePath, ...]
    total_surface_area: float
    internal_vector: FloatArray
    solar_vector: FloatArray
    hvac_vector: FloatArray
    operative_vector: FloatArray
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
    t_mean_radiant: FloatArray | None = None
    transparent_node_temperatures: dict[str, FloatArray] | None = None
    unmet_heating_k: FloatArray | None = None
    unmet_cooling_k: FloatArray | None = None


def _arr(value: Any) -> FloatArray:
    return cast(FloatArray, np.asarray(value, dtype=np.float64))


def _hourly(value: float | FloatArray, n: int, name: str) -> FloatArray:
    a = _arr(value)
    if a.ndim == 0:
        a = _arr(np.full(n, float(a)))
    if a.shape != (n,) or not np.isfinite(a).all():
        raise ValueError(f"{name} must be scalar or one finite value per hour")
    return a


def _rsi(element: Any) -> float:
    tilt = float(getattr(element, "inclination", 90.0))
    return 0.10 if tilt < 60.0 else (0.17 if tilt > 120.0 else 0.13)


def _film(element: Any, strict: bool) -> Film:
    fields = ("h_ci_w_m2k", "h_ri_w_m2k", "h_ce_w_m2k", "h_re_w_m2k")
    values = [getattr(element, field, None) for field in fields]
    if all(value is not None for value in values):
        result = Film(*(float(value) for value in values))
        if min(result.h_ci, result.h_ri, result.h_ce, result.h_re) < 0.0:
            raise ValueError(f"Negative surface coefficient on '{element.id}'")
        return result
    if strict:
        missing = [field for field, value in zip(fields, values, strict=True) if value is None]
        raise ValueError(
            f"Strict ISO 52016 mode requires surface coefficients for '{element.id}': "
            + ", ".join(missing)
        )
    h_i = 1.0 / _rsi(element)
    h_ri = min(5.0, max(h_i - 0.1, 0.0))
    return Film(max(h_i - h_ri, 0.1), h_ri, 20.0, 5.0, True)


def _capacity_fractions(kind: str | None) -> FloatArray:
    # Compatibility fallback only. Ordering is exterior -> interior.
    values = {
        "internal": [0.02, 0.06, 0.12, 0.25, 0.55],
        "external": [0.55, 0.25, 0.12, 0.06, 0.02],
        "middle": [0.05, 0.15, 0.60, 0.15, 0.05],
        "internal_external": [0.40, 0.08, 0.04, 0.08, 0.40],
        "distributed": [0.20] * 5,
    }
    return _arr(values.get(kind or "distributed", values["distributed"]))


def _opaque_core(element: OpaqueElement, film: Film, strict: bool) -> tuple[FloatArray, FloatArray, bool]:
    resistances = getattr(element, "thermal_node_resistances_m2k_w", None)
    capacities = getattr(element, "thermal_node_capacities_kj_m2k", None)
    inferred = film.inferred
    if resistances is not None:
        r = _arr(resistances)
        if r.shape == (6,):
            if strict:
                raise ValueError(
                    f"'{element.id}' uses legacy six-resistance data including surface films; "
                    "strict mode requires four core resistances"
                )
            r = r[1:5]
            inferred = True
        if r.shape != (4,) or np.any(r <= 0.0):
            raise ValueError(f"'{element.id}' requires four positive core resistances")
    else:
        if strict:
            raise ValueError(f"Strict ISO 52016 mode requires core resistances for '{element.id}'")
        r_core = 1.0 / float(element.u_value) - 1.0 / (film.h_ci + film.h_ri) - 1.0 / (film.h_ce + film.h_re)
        if r_core <= 0.0:
            raise ValueError(f"'{element.id}' U-value is incompatible with positive core resistance")
        r = _arr(np.full(4, r_core / 4.0))
        inferred = True
    if capacities is not None:
        c = _arr(capacities)
        if c.shape != (5,) or np.any(c < 0.0) or c.sum() <= 0.0:
            raise ValueError(f"'{element.id}' requires five non-negative node capacities")
    else:
        if strict:
            raise ValueError(f"Strict ISO 52016 mode requires node capacities for '{element.id}'")
        areal = float(getattr(element, "areal_heat_capacity", None) or DEFAULT_AREAL_CAPACITY_KJ_M2K)
        c = areal * _capacity_fractions(getattr(element, "mass_distribution_class", None))
        inferred = True
    return r, _arr(c * float(element.area) * 1000.0), inferred


def _sky_view(element: Any) -> float:
    explicit = getattr(element, "sky_view_factor", None)
    value = float(explicit) if explicit is not None else 0.5 * (1.0 + np.cos(np.deg2rad(float(element.inclination))))
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"sky_view_factor for '{element.id}' must be 0..1")
    return value


def _bridge_paths(bridges: ThermalBridgeConfig, zone_id: str, t_e: FloatArray, opaque: Mapping[str, OpaqueElement]) -> tuple[BridgePath, ...]:
    result: list[BridgePath] = []
    for bridge in [*bridges.linear_bridges, *bridges.point_bridges]:
        if bridge.zone_id != zone_id:
            continue
        h = float(bridge.psi_value) * float(bridge.length) if hasattr(bridge, "psi_value") else float(bridge.chi_value) * int(bridge.count)
        if h <= 0.0:
            continue
        host = opaque.get(getattr(bridge, "element_id", None))
        adjacent = getattr(bridge, "adjacent_space_type", None) or (host.adjacent_space_type if host else AdjacentSpaceType.OUTDOOR)
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
        result.append(BridgePath(h, boundary))
    return tuple(result)


def _distribution(surfaces: Sequence[Surface], explicit: Mapping[str, float] | None) -> FloatArray:
    if explicit:
        known = {surface.element_id for surface in surfaces}
        unknown = set(explicit) - known
        if unknown:
            raise ValueError("Unknown surface IDs in radiant distribution: " + ", ".join(sorted(unknown)))
        values = _arr([float(explicit.get(surface.element_id, 0.0)) for surface in surfaces])
        if np.any(values < 0.0) or not np.isclose(values.sum(), 1.0, atol=1e-6):
            raise ValueError("Radiant distribution factors must be non-negative and sum to 1")
        return values
    areas = _arr([surface.area for surface in surfaces])
    return areas / areas.sum()


def _prepare(*, opaque_elements: list[OpaqueElement], transparent_elements: Sequence[Any], bridges: ThermalBridgeConfig,
             zone_id: str, t_e: FloatArray, opaque_solar: Mapping[str, FloatArray], sky_delta: FloatArray,
             air_capacity_j_k: float, f_int_c: float, f_sol_c: float, f_hvac_c: float,
             operative_air_weight: float, solar_distribution: Mapping[str, float] | None, strict: bool) -> Prepared:
    selected_opaque = [element for element in opaque_elements if element.zone_id == zone_id]
    selected_windows = [element for element in transparent_elements if element.zone_id == zone_id]
    n_nodes = 1 + 5 * len(selected_opaque) + 2 * len(selected_windows)
    matrix = _arr(np.zeros((n_nodes, n_nodes)))
    storage = _arr(np.zeros(n_nodes))
    storage[0] = air_capacity_j_k / DT
    matrix[0, 0] += storage[0]
    opaque_paths: list[OpaquePath] = []
    window_paths: list[WindowPath] = []
    surfaces: list[Surface] = []
    cursor = 1

    for element in selected_opaque:
        if element.adjacent_space_type == AdjacentSpaceType.HEATED_ZONE:
            if strict:
                raise ValueError(f"'{element.id}' needs the coupled-zone path for a heated adjacent zone")
            continue
        film = _film(element, strict)
        area = float(element.area)
        boundary = _arr(adjacent_temperature(element, t_e))
        is_ground = element.adjacent_space_type == AdjacentSpaceType.GROUND
        if is_ground:
            film = Film(film.h_ci, film.h_ri, 0.0, 0.0, film.inferred)
            r_ground = getattr(element, "ground_virtual_resistance_m2k_w", None)
            if r_ground is None:
                if strict:
                    raise ValueError(f"Ground element '{element.id}' requires ground_virtual_resistance_m2k_w")
                r_ground = max(1.0 / float(element.u_value) - _rsi(element), 1e-6)
            h_boundary = area / float(r_ground)
            solar = _arr(np.zeros(len(t_e)))
            sky = _arr(np.zeros(len(t_e)))
            # Ground virtual layer is the exterior path; core inference must not subtract an exterior film.
            if getattr(element, "thermal_node_resistances_m2k_w", None) is None and not strict:
                total_core = 1.0 / float(element.u_value) - 1.0 / (film.h_ci + film.h_ri) - float(r_ground)
                if total_core <= 0.0:
                    total_core = max(1.0 / float(element.u_value) - 1.0 / (film.h_ci + film.h_ri), 1e-6)
                r = _arr(np.full(4, total_core / 4.0))
                capacities = getattr(element, "thermal_node_capacities_kj_m2k", None)
                if capacities is None:
                    areal = float(getattr(element, "areal_heat_capacity", None) or DEFAULT_AREAL_CAPACITY_KJ_M2K)
                    c = areal * _capacity_fractions(getattr(element, "mass_distribution_class", None))
                else:
                    c = _arr(capacities)
                c = _arr(c * area * 1000.0)
                inferred = True
            else:
                r, c, inferred = _opaque_core(element, Film(film.h_ci, film.h_ri, 1.0, 0.0, film.inferred), strict)
        else:
            h_boundary = area * (film.h_ce + film.h_re)
            solar = _hourly(opaque_solar.get(element.id, np.zeros(len(t_e))), len(t_e), f"solar {element.id}")
            sky = area * _sky_view(element) * film.h_re * sky_delta
            r, c, inferred = _opaque_core(element, film, strict)
        idx = cast(tuple[int, int, int, int, int], tuple(range(cursor, cursor + 5)))
        cursor += 5
        h_core = area / r
        for local, node in enumerate(idx):
            storage[node] = c[local] / DT
            matrix[node, node] += storage[node]
        for link, h in enumerate(h_core):
            left, right = idx[link], idx[link + 1]
            matrix[left, left] += h; matrix[right, right] += h
            matrix[left, right] -= h; matrix[right, left] -= h
        ext, interior = idx[0], idx[4]
        matrix[ext, ext] += h_boundary
        h_ci = area * film.h_ci
        matrix[0, 0] += h_ci; matrix[0, interior] -= h_ci
        matrix[interior, interior] += h_ci; matrix[interior, 0] -= h_ci
        surfaces.append(Surface(element.id, interior, area, film.h_ri))
        opaque_paths.append(OpaquePath(element, idx, boundary, h_boundary, solar, _arr(sky), c, inferred or film.inferred))

    for element in selected_windows:
        film = _film(element, strict)
        area = float(element.area)
        r_core = getattr(element, "core_thermal_resistance_m2k_w", None)
        inferred = film.inferred
        if r_core is None:
            if strict:
                raise ValueError(f"Window '{element.id}' requires core_thermal_resistance_m2k_w")
            r_core = 1.0 / float(element.u_value) - 1.0 / (film.h_ci + film.h_ri) - 1.0 / (film.h_ce + film.h_re)
            inferred = True
        if float(r_core) <= 0.0:
            raise ValueError(f"Window '{element.id}' has non-positive core resistance")
        ext, interior = cursor, cursor + 1; cursor += 2
        h_core = area / float(r_core); h_boundary = area * (film.h_ce + film.h_re)
        matrix[ext, ext] += h_core + h_boundary; matrix[interior, interior] += h_core
        matrix[ext, interior] -= h_core; matrix[interior, ext] -= h_core
        h_ci = area * film.h_ci
        matrix[0, 0] += h_ci; matrix[0, interior] -= h_ci
        matrix[interior, interior] += h_ci; matrix[interior, 0] -= h_ci
        surfaces.append(Surface(element.id, interior, area, film.h_ri))
        window_paths.append(WindowPath(element, (ext, interior), t_e, h_boundary, inferred))

    if not surfaces:
        raise ValueError("ISO 52016 zone requires at least one internal surface")
    area_total = float(sum(surface.area for surface in surfaces))
    for si in surfaces:
        g = si.area * si.h_ri
        matrix[si.index, si.index] += g
        for sj in surfaces:
            matrix[si.index, sj.index] -= g * sj.area / area_total

    opaque_by_id = {element.id: element for element in selected_opaque}
    bridge_paths = _bridge_paths(bridges, zone_id, t_e, opaque_by_id)
    for bridge in bridge_paths:
        matrix[0, 0] += bridge.h

    dist = _distribution(surfaces, None)
    sol_dist = _distribution(surfaces, solar_distribution)
    internal_vec = _arr(np.zeros(n_nodes)); internal_vec[0] = f_int_c
    solar_vec = _arr(np.zeros(n_nodes)); solar_vec[0] = f_sol_c
    hvac_vec = _arr(np.zeros(n_nodes)); hvac_vec[0] = f_hvac_c
    operative = _arr(np.zeros(n_nodes)); operative[0] = operative_air_weight
    for d, sd, surface in zip(dist, sol_dist, surfaces, strict=True):
        internal_vec[surface.index] += (1.0 - f_int_c) * d
        solar_vec[surface.index] += (1.0 - f_sol_c) * sd
        hvac_vec[surface.index] += (1.0 - f_hvac_c) * d
        operative[surface.index] += (1.0 - operative_air_weight) * surface.area / area_total
    return Prepared(matrix, storage, cast(NDArray[np.bool_], storage > 0.0), tuple(opaque_paths), tuple(window_paths),
                    tuple(surfaces), bridge_paths, area_total, internal_vec, solar_vec, hvac_vec, operative,
                    any(path.inferred for path in opaque_paths) or any(path.inferred for path in window_paths))


def _temperatures(prepared: Prepared, state: FloatArray) -> tuple[float, float, float]:
    air = float(state[0])
    mrt = float(sum(surface.area * state[surface.index] for surface in prepared.surfaces) / prepared.total_surface_area)
    operative = float(prepared.operative_vector @ state)
    return air, mrt, operative


def _cycle(prepared: Prepared, h_ve: FloatArray, t_supply: FloatArray, phi_int: FloatArray, phi_sol: FloatArray,
           heat_set: FloatArray | None, cool_set: FloatArray | None, max_heat: FloatArray | None, max_cool: FloatArray | None,
           previous: FloatArray) -> tuple[ISO52016ZoneSolution, FloatArray]:
    n = len(t_supply); size = prepared.matrix.shape[0]
    outputs = [_arr(np.zeros(n)) for _ in range(10)]
    t_air, t_mrt, t_op, t_mass, t_mass_mean, q_h, q_c, q_tr, unmet_h, unmet_c = outputs
    opaque_history = {path.element.id: _arr(np.empty((n, 5))) for path in prepared.opaque}
    window_history = {path.element.id: _arr(np.empty((n, 2))) for path in prepared.windows}
    cache: dict[float, FloatArray] = {}
    state_prev = previous.copy()
    for hour in range(n):
        key = round(float(h_ve[hour]), 12)
        inv = cache.get(key)
        if inv is None:
            m = prepared.matrix.copy(); m[0, 0] += h_ve[hour]
            inv = _arr(np.linalg.inv(m)); cache[key] = inv
        rhs = prepared.storage * state_prev
        rhs = _arr(rhs + prepared.internal_vector * phi_int[hour] + prepared.solar_vector * phi_sol[hour])
        rhs[0] += h_ve[hour] * t_supply[hour]
        for bridge in prepared.bridges:
            rhs[0] += bridge.h * bridge.boundary[hour]
        for path in prepared.opaque:
            ext = path.indices[0]
            rhs[ext] += path.h_boundary * path.boundary[hour] + path.solar_w[hour] - path.sky_w[hour]
        for path in prepared.windows:
            rhs[path.indices[0]] += path.h_boundary * path.boundary[hour]
        free = _arr(inv @ rhs)
        free_op = _temperatures(prepared, free)[2]
        response = _arr(inv @ prepared.hvac_vector)
        op_response = float(prepared.operative_vector @ response)
        if op_response <= 0.0:
            raise ValueError("Non-positive operative response to HVAC")
        phi = 0.0
        hs = None if heat_set is None else float(heat_set[hour]); cs = None if cool_set is None else float(cool_set[hour])
        if hs is not None and free_op < hs - 1e-9:
            phi = (hs - free_op) / op_response
            if max_heat is not None: phi = min(phi, float(max_heat[hour]))
            q_h[hour] = max(phi, 0.0)
        elif cs is not None and free_op > cs + 1e-9:
            phi = (cs - free_op) / op_response
            if max_cool is not None: phi = max(phi, -float(max_cool[hour]))
            q_c[hour] = max(-phi, 0.0)
        current = free if phi == 0.0 else _arr(free + phi * response)
        air, mrt, operative = _temperatures(prepared, current)
        t_air[hour], t_mrt[hour], t_op[hour] = air, mrt, operative
        if hs is not None: unmet_h[hour] = max(hs - operative, 0.0)
        if cs is not None: unmet_c[hour] = max(operative - cs, 0.0)
        capacity = prepared.storage * DT; total_c = float(capacity.sum())
        if total_c > 0.0:
            t_mass[hour] = float(capacity @ current / total_c)
            t_mass_mean[hour] = float(capacity @ (0.5 * (state_prev + current)) / total_c)
        else:
            t_mass[hour] = t_mass_mean[hour] = air
        outward = sum(bridge.h * (air - bridge.boundary[hour]) for bridge in prepared.bridges)
        for path in prepared.opaque:
            outward += path.h_boundary * (current[path.indices[0]] - path.boundary[hour])
            opaque_history[path.element.id][hour, :] = current[list(path.indices)]
        for path in prepared.windows:
            outward += path.h_boundary * (current[path.indices[0]] - path.boundary[hour])
            window_history[path.element.id][hour, :] = current[list(path.indices)]
        q_tr[hour] = outward
        state_prev = current.copy()
    return ISO52016ZoneSolution(t_air, t_op, t_mass, t_mass_mean, t_mrt, q_h, q_c, q_tr, opaque_history,
                                prepared.inferred, 0.0, t_mrt, window_history, unmet_h, unmet_c), state_prev


def solve_zone_iso52016(*, opaque_elements: list[OpaqueElement], transparent_elements: Sequence[Any],
                         bridges: ThermalBridgeConfig, zone_id: str, h_ve: float | FloatArray,
                         t_e: FloatArray, phi_int: FloatArray, phi_sol_transparent: FloatArray,
                         opaque_solar_absorbed_w_by_element: Mapping[str, FloatArray],
                         t_set_heating: float | FloatArray | None, t_set_cooling: float | FloatArray | None,
                         t_supply: FloatArray | None = None, internal_convective_fraction: float = 0.4,
                         solar_convective_fraction: float = 0.1, hvac_convective_fraction: float = 1.0,
                         operative_air_weight: float = 0.5, air_furniture_heat_capacity_j_k: float | None = None,
                         floor_area_m2: float | None = None, sky_temperature_difference_k: float | FloatArray = 11.0,
                         solar_radiant_distribution: Mapping[str, float] | None = None,
                         max_heating_power_w: float | FloatArray | None = None,
                         max_cooling_power_w: float | FloatArray | None = None,
                         require_explicit_construction_nodes: bool = False, strict_conformance: bool | None = None,
                         max_warmup_cycles: int = 20, warmup_tolerance_k: float = 0.01) -> ISO52016ZoneSolution:
    outdoor = _arr(t_e); n = len(outdoor)
    if n == 0: raise ValueError("Hourly solver requires at least one hour")
    strict = require_explicit_construction_nodes if strict_conformance is None else bool(strict_conformance)
    ventilation = _hourly(h_ve, n, "h_ve"); supply = outdoor if t_supply is None else _hourly(t_supply, n, "t_supply")
    internal = _hourly(phi_int, n, "phi_int"); solar = _hourly(phi_sol_transparent, n, "phi_sol_transparent")
    sky = _hourly(sky_temperature_difference_k, n, "sky_temperature_difference_k")
    for name, value in (("internal_convective_fraction", internal_convective_fraction), ("solar_convective_fraction", solar_convective_fraction),
                        ("hvac_convective_fraction", hvac_convective_fraction), ("operative_air_weight", operative_air_weight)):
        if not 0.0 <= float(value) <= 1.0: raise ValueError(f"{name} must be 0..1")
    if air_furniture_heat_capacity_j_k is None:
        if strict: raise ValueError("Strict ISO 52016 mode requires air_furniture_heat_capacity_j_k")
        area = float(floor_area_m2 or max(sum(float(e.area) for e in opaque_elements) / 2.5, 1.0))
        air_furniture_heat_capacity_j_k = DEFAULT_AIR_FURNITURE_CAPACITY_KJ_M2K * area * 1000.0
    prepared = _prepare(opaque_elements=opaque_elements, transparent_elements=transparent_elements, bridges=bridges,
                        zone_id=zone_id, t_e=outdoor, opaque_solar=opaque_solar_absorbed_w_by_element, sky_delta=sky,
                        air_capacity_j_k=float(air_furniture_heat_capacity_j_k), f_int_c=float(internal_convective_fraction),
                        f_sol_c=float(solar_convective_fraction), f_hvac_c=float(hvac_convective_fraction),
                        operative_air_weight=float(operative_air_weight), solar_distribution=solar_radiant_distribution, strict=strict)
    heat = None if t_set_heating is None else _hourly(t_set_heating, n, "t_set_heating")
    cool = None if t_set_cooling is None else _hourly(t_set_cooling, n, "t_set_cooling")
    max_h = None if max_heating_power_w is None else _hourly(max_heating_power_w, n, "max_heating_power_w")
    max_c = None if max_cooling_power_w is None else _hourly(max_cooling_power_w, n, "max_cooling_power_w")
    initial = float(heat[0] if heat is not None else (cool[0] if cool is not None else outdoor[0]))
    previous = _arr(np.full(prepared.matrix.shape[0], initial)); cycles = max_warmup_cycles if n == 8760 else 1
    solution: ISO52016ZoneSolution | None = None; residual = 0.0
    for _ in range(cycles):
        start = previous.copy()
        solution, previous = _cycle(prepared, ventilation, supply, internal, solar, heat, cool, max_h, max_c, start)
        mask = prepared.capacity_mask
        residual = float(np.max(np.abs(previous[mask] - start[mask]))) if np.any(mask) else 0.0
        if cycles == 1 or residual <= warmup_tolerance_k:
            if cycles > 1:
                solution, _ = _cycle(prepared, ventilation, supply, internal, solar, heat, cool, max_h, max_c, previous)
            break
    if solution is None: raise RuntimeError("Hourly ISO 52016 solver did not produce a solution")
    if n == 8760 and residual > warmup_tolerance_k:
        raise RuntimeError(f"Hourly ISO 52016 solver did not reach periodic state: residual={residual:.6f} K")
    solution.periodic_residual_k = residual
    return solution
