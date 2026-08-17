"""Compatibility layer for the historical 5R1C solver.

The legacy 5R1C model remains available for old analytical projects. Periodic
warm-up is an explicit option so low-level unit callers can still inspect a
single cold-start cycle. Production annual calculations request warm-up
explicitly; the repaired default hourly engine uses the separate
per-construction solver in ``iso52016_hourly.py``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

_LEGACY_NAME = "app.engine._legacy_thermal_balance"
_LEGACY_PATH = Path(__file__).resolve().parent.parent / "thermal_balance.py"
_spec = importlib.util.spec_from_file_location(_LEGACY_NAME, _LEGACY_PATH)
if _spec is None or _spec.loader is None:  # pragma: no cover
    raise ImportError(f"Cannot load legacy thermal balance from {_LEGACY_PATH}")
_legacy = importlib.util.module_from_spec(_spec)
sys.modules[_LEGACY_NAME] = _legacy
_spec.loader.exec_module(_legacy)

for _name in dir(_legacy):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_legacy, _name)


def _solve_zone_cycle(
    *,
    network,
    h_ve_hourly: np.ndarray,
    t_e: np.ndarray,
    t_sup: np.ndarray,
    phi_int: np.ndarray,
    phi_sol: np.ndarray,
    properties,
    t_set_heating: float | None,
    t_set_cooling: float | None,
    initial_mass_temperature: float,
):
    """Solve one climate cycle and return (solution, final mass temperature)."""
    n = len(t_e)
    h_is = properties.h_tr_is
    h_ms = properties.h_tr_ms
    h_op = network.h_opaque
    h_em = opaque_external_conductance(h_op, h_ms)
    h_surface_total = sum(network.h_surface)
    t_opaque = network.t_opaque if network.t_opaque is not None else np.zeros(n, dtype=float)

    frac_mass = properties.area_mass / properties.area_total_internal
    frac_surface = max(
        0.0,
        1.0 - frac_mass - h_surface_total / (H_MS_W_M2K * properties.area_total_internal),
    )
    phi_ia = 0.5 * phi_int
    phi_rest = 0.5 * phi_int + phi_sol
    phi_m = frac_mass * phi_rest
    phi_st = frac_surface * phi_rest

    dt = SECONDS_PER_HOUR
    a11 = properties.capacity + 0.5 * dt * (h_ms + h_em)
    a11_rhs = properties.capacity - 0.5 * dt * (h_ms + h_em)
    a33 = h_is + h_ms + h_surface_total

    t_air = np.empty(n, dtype=float)
    t_op = np.empty(n, dtype=float)
    t_mass = np.empty(n, dtype=float)
    t_mass_mean = np.empty(n, dtype=float)
    t_surface = np.empty(n, dtype=float)
    q_h = np.zeros(n, dtype=float)
    q_c = np.zeros(n, dtype=float)

    t_m_prev = float(initial_mass_temperature)
    for t in range(n):
        t_m_previous = t_m_prev
        h_ve_t = h_ve_hourly[t]
        matrix = np.array(
            [
                [a11, 0.0, -dt * h_ms],
                [0.0, h_is + h_ve_t, -h_is],
                [-0.5 * h_ms, -h_is, a33],
            ],
            dtype=float,
        )
        unit = np.linalg.solve(matrix, np.array([0.0, 1.0, 0.0]))
        d_theta_air_per_w = float(unit[1])
        if d_theta_air_per_w <= 0.0:
            raise ValueError("5R1C network is singular: air node insensitive to heating")

        surface_drive = sum(
            h * ts[t] for h, ts in zip(network.h_surface, network.t_surface, strict=True)
        )
        rhs = np.array(
            [
                a11_rhs * t_m_prev + dt * (phi_m[t] + h_em * t_opaque[t]),
                h_ve_t * t_sup[t] + phi_ia[t],
                phi_st[t] + surface_drive + 0.5 * h_ms * t_m_prev,
            ],
            dtype=float,
        )
        x0 = np.linalg.solve(matrix, rhs)
        theta_air_free = float(x0[1])
        phi_hc = 0.0
        eps = 1e-9
        if t_set_heating is not None and theta_air_free < t_set_heating - eps:
            phi_hc = (t_set_heating - theta_air_free) / d_theta_air_per_w
            q_h[t] = phi_hc
        elif t_set_cooling is not None and theta_air_free > t_set_cooling + eps:
            phi_hc = (t_set_cooling - theta_air_free) / d_theta_air_per_w
            q_c[t] = -phi_hc

        x = x0 if phi_hc == 0.0 else x0 + phi_hc * unit
        t_mass[t] = x[0]
        t_mass_mean[t] = 0.5 * (t_m_previous + x[0])
        t_surface[t] = x[2]
        t_air[t] = x[1]
        t_op[t] = 0.3 * x[1] + 0.7 * x[2]
        t_m_prev = float(x[0])

    return (
        ZoneSolution(
            t_air=t_air,
            t_operative=t_op,
            t_mass=t_mass,
            t_mass_mean=t_mass_mean,
            t_surface=t_surface,
            q_heating=q_h,
            q_cooling=q_c,
        ),
        t_m_prev,
    )


def solve_zone_5r1c(
    *,
    network,
    h_ve: float | np.ndarray,
    t_e: np.ndarray,
    phi_int: np.ndarray,
    phi_sol: np.ndarray,
    properties,
    t_set_heating: float | None,
    t_set_cooling: float | None,
    t_supply: np.ndarray | None = None,
    periodic_warmup: bool = False,
    max_warmup_cycles: int = 30,
    warmup_tolerance_k: float = 1e-8,
):
    """Solve the reduced 5R1C model, optionally from a periodic annual state."""
    t_e = np.asarray(t_e, dtype=float)
    t_sup = t_e if t_supply is None else np.asarray(t_supply, dtype=float)
    phi_int = np.asarray(phi_int, dtype=float)
    phi_sol = np.asarray(phi_sol, dtype=float)
    n = len(t_e)
    for name, values in (
        ("t_supply", t_sup),
        ("phi_int", phi_int),
        ("phi_sol", phi_sol),
    ):
        if values.shape != (n,):
            raise ValueError(f"{name} must contain one value per simulation hour")
        if not np.isfinite(values).all():
            raise ValueError(f"{name} must contain finite values")

    h_ve_input = np.asarray(h_ve, dtype=float)
    if h_ve_input.ndim == 0:
        h_ve_hourly = np.full(n, float(h_ve_input), dtype=float)
    elif h_ve_input.shape == (n,):
        h_ve_hourly = h_ve_input
    else:
        raise ValueError("h_ve must be a scalar or contain one value per hour")
    if not np.isfinite(h_ve_hourly).all() or np.any(h_ve_hourly < 0.0):
        raise ValueError("h_ve must contain finite non-negative values")
    if max_warmup_cycles < 1:
        raise ValueError("max_warmup_cycles must be positive")
    if warmup_tolerance_k <= 0.0:
        raise ValueError("warmup_tolerance_k must be positive")

    initial = (
        float(t_set_heating)
        if t_set_heating is not None
        else float(t_set_cooling if t_set_cooling is not None else t_e[0])
    )
    cycles = max_warmup_cycles if periodic_warmup and n == 8760 else 1
    solution = None
    for _ in range(cycles):
        solution, final_mass = _solve_zone_cycle(
            network=network,
            h_ve_hourly=h_ve_hourly,
            t_e=t_e,
            t_sup=t_sup,
            phi_int=phi_int,
            phi_sol=phi_sol,
            properties=properties,
            t_set_heating=t_set_heating,
            t_set_cooling=t_set_cooling,
            initial_mass_temperature=initial,
        )
        if cycles == 1:
            break
        residual = abs(final_mass - initial)
        initial = final_mass
        if residual <= warmup_tolerance_k:
            solution, _ = _solve_zone_cycle(
                network=network,
                h_ve_hourly=h_ve_hourly,
                t_e=t_e,
                t_sup=t_sup,
                phi_int=phi_int,
                phi_sol=phi_sol,
                properties=properties,
                t_set_heating=t_set_heating,
                t_set_cooling=t_set_cooling,
                initial_mass_temperature=initial,
            )
            break
    if solution is None:  # pragma: no cover
        raise RuntimeError("5R1C solver did not produce a solution")
    return solution


_legacy.solve_zone_5r1c = solve_zone_5r1c
