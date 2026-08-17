"""Compatibility façade for the rebuilt PN-EN ISO 52016-1 hourly solver.

The underlying implementation lives in the historical sibling module
``iso52016_hourly.py``. This package separates legacy compatibility from full
strict conformance and patches boundary conditions that must not be silently
approximated in strict mode.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

from app.schemas.models import AdjacentSpaceType

_LEGACY_NAME = "app.engine._iso52016_hourly_core"
_LEGACY_PATH = Path(__file__).resolve().parent.parent / "iso52016_hourly.py"
_spec = importlib.util.spec_from_file_location(_LEGACY_NAME, _LEGACY_PATH)
if _spec is None or _spec.loader is None:  # pragma: no cover
    raise ImportError(f"Cannot load ISO 52016 core from {_LEGACY_PATH}")
_core = importlib.util.module_from_spec(_spec)
sys.modules[_LEGACY_NAME] = _core
_spec.loader.exec_module(_core)
for _name in dir(_core):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_core, _name)

_core_solve = _core.solve_zone_iso52016
_core_prepare = _core._prepare
_core_adjacent_temperature = _core.adjacent_temperature


def _construction_inputs_are_explicit(opaque_elements, zone_id: str) -> bool:
    selected = [element for element in opaque_elements if element.zone_id == zone_id]
    return bool(selected) and all(
        getattr(element, "thermal_node_capacities_kj_m2k", None) is not None
        and getattr(element, "thermal_node_resistances_m2k_w", None) is not None
        for element in selected
    )


def _adjacent_temperature(element, t_e, unheated_zone_temperature=None, T_int=None):
    if element.adjacent_space_type == AdjacentSpaceType.UNHEATED_ZONE:
        explicit = getattr(element, "adjacent_temperature", None)
        if explicit is not None:
            return np.full(len(np.asarray(t_e)), float(explicit), dtype=float)
    return _core_adjacent_temperature(
        element,
        t_e,
        unheated_zone_temperature=unheated_zone_temperature,
        T_int=T_int,
    )


def _preserve_legacy_six_resistance_path(prepared, *, strict: bool):
    """Keep the complete R-path represented by historical six-value inputs.

    The legacy representation stores six resistances from room air to the
    exterior boundary: the first and last values contain the surface film plus
    half of the adjacent finite-volume interval, while the four middle values
    connect the five construction-node centres.

    The rebuilt core already uses the four middle values between its five
    nodes. Without this correction, simply slicing ``r[1:5]`` drops both
    half-node resistances and shortens the total thermal path.

    Explicit surface coefficients can also be used when they represent a
    *combined*, non-radiative film (``h_ri=h_re=0``). This is needed by
    benchmarks such as ASHRAE 140, which prescribe combined inside/outside
    surface coefficients. A split convective/radiative surface network is not
    collapsed here because that would destroy the separate radiant exchange.
    """
    if strict:
        return prepared

    matrix = prepared.matrix.copy()
    patched_opaque = []
    changed = False

    for path in prepared.opaque:
        resistances = getattr(path.element, "thermal_node_resistances_m2k_w", None)
        if resistances is None or len(resistances) != 6:
            patched_opaque.append(path)
            continue

        film = _core._film(path.element, False)
        has_split_radiation = not film.inferred and (film.h_ri > 0.0 or film.h_re > 0.0)
        if has_split_radiation:
            patched_opaque.append(path)
            continue

        values = np.asarray(resistances, dtype=float)
        area = float(path.element.area)
        ext, interior = path.indices[0], path.indices[4]

        desired_boundary_h = area / float(values[-1])
        boundary_delta = desired_boundary_h - float(path.h_boundary)
        matrix[ext, ext] += boundary_delta

        old_room_h = area * float(film.h_ci)
        desired_room_h = area / float(values[0])
        room_delta = desired_room_h - old_room_h
        matrix[0, 0] += room_delta
        matrix[0, interior] -= room_delta
        matrix[interior, interior] += room_delta
        matrix[interior, 0] -= room_delta

        exterior_film_h = float(film.h_ce + film.h_re)
        exterior_film_r = 1.0 / exterior_film_h if exterior_film_h > 0.0 else 0.0
        surface_source_fraction = min(
            max(exterior_film_r / float(values[-1]), 0.0),
            1.0,
        )

        patched_opaque.append(
            replace(
                path,
                h_boundary=desired_boundary_h,
                solar_w=np.asarray(path.solar_w, dtype=float) * surface_source_fraction,
                sky_w=np.asarray(path.sky_w, dtype=float) * surface_source_fraction,
            )
        )
        changed = True

    if not changed:
        return prepared
    return replace(prepared, matrix=matrix, opaque=tuple(patched_opaque))


def _prepare(*args, **kwargs):
    prepared = _core_prepare(*args, **kwargs)
    strict = bool(kwargs.get("strict", False))
    prepared = _preserve_legacy_six_resistance_path(prepared, strict=strict)

    t_e = np.asarray(kwargs["t_e"], dtype=float)
    sky_delta = np.asarray(kwargs["sky_delta"], dtype=float)
    if sky_delta.ndim == 0:
        sky_delta = np.full(len(t_e), float(sky_delta), dtype=float)

    patched_windows = []
    for path in prepared.windows:
        film = _core._film(path.element, strict)
        view = _core._sky_view(path.element)
        total_external = film.h_ce + film.h_re
        if total_external <= 0.0:
            boundary = path.boundary
        else:
            boundary = (
                np.asarray(path.boundary, dtype=float)
                - (film.h_re / total_external) * view * sky_delta
            )
        patched_windows.append(replace(path, boundary=np.asarray(boundary, dtype=float)))
    return replace(prepared, windows=tuple(patched_windows))


_core.adjacent_temperature = _adjacent_temperature
_core._prepare = _prepare


def solve_zone_iso52016(*args, **kwargs):
    require_nodes = bool(kwargs.get("require_explicit_construction_nodes", False))
    strict_raw = kwargs.get("strict_conformance")
    strict = bool(strict_raw) if strict_raw is not None else False
    opaque = kwargs.get("opaque_elements")
    zone_id = kwargs.get("zone_id")
    if opaque is None or zone_id is None:
        raise TypeError(
            "solve_zone_iso52016 requires opaque_elements and zone_id as keyword arguments"
        )

    if require_nodes and not _construction_inputs_are_explicit(opaque, zone_id):
        raise ValueError(
            "explicit five-node construction data are required: provide "
            "thermal_node_capacities_kj_m2k and thermal_node_resistances_m2k_w "
            "for every opaque element in the zone."
        )

    if strict:
        for element in opaque:
            if element.zone_id != zone_id:
                continue
            if (
                element.adjacent_space_type == AdjacentSpaceType.UNHEATED_ZONE
                and getattr(element, "adjacent_temperature", None) is None
            ):
                raise ValueError(
                    f"Strict ISO 52016 mode requires a verified adjacent-zone temperature "
                    f"for unconditioned boundary '{element.id}'; the compatibility T_e+3 K "
                    "heuristic is not permitted."
                )

    kwargs["require_explicit_construction_nodes"] = False
    kwargs["strict_conformance"] = strict

    if not strict:
        kwargs["operative_air_weight"] = 1.0
        kwargs["sky_temperature_difference_k"] = 0.0

    result = _core_solve(*args, **kwargs)
    if require_nodes and not strict and _construction_inputs_are_explicit(opaque, zone_id):
        result.used_inferred_construction = False
    return result


_core.solve_zone_iso52016 = solve_zone_iso52016
