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


def _prepare(*args, **kwargs):
    prepared = _core_prepare(*args, **kwargs)
    strict = bool(kwargs.get("strict", False))
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
            # Linearized window exterior balance represented by an exactly
            # equivalent boundary temperature including long-wave sky loss.
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

    # Construction explicitness is checked by this façade. The core receives
    # only the actual strict-conformance intent.
    kwargs["require_explicit_construction_nodes"] = False
    kwargs["strict_conformance"] = strict

    if not strict:
        # Compatibility mode intentionally reproduces the historical air-
        # temperature thermostat and omits a guessed Annex-B sky delta. It is
        # explicitly reported as non-conformant by preflight_systems.py.
        kwargs["operative_air_weight"] = 1.0
        kwargs["sky_temperature_difference_k"] = 0.0

    result = _core_solve(*args, **kwargs)
    if require_nodes and not strict and _construction_inputs_are_explicit(opaque, zone_id):
        result.used_inferred_construction = False
    return result


_core.solve_zone_iso52016 = solve_zone_iso52016
