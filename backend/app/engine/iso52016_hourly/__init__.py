"""Compatibility façade for the rebuilt PN-EN ISO 52016-1 hourly solver.

The underlying implementation lives in the historical sibling module
``iso52016_hourly.py``.  This package deliberately separates two concepts that
older callers combined:

* ``require_explicit_construction_nodes`` requires explicit construction-node
  capacities/resistances, but may accept the historical six-resistance format;
* ``strict_conformance`` additionally requires all EPB-delegated surface,
  ground, sky and zone inputs and is the only mode that may be reported as a
  strict ISO 52016 calculation.

Non-strict compatibility calls also keep long-wave sky loss disabled unless a
future explicit compatibility input is introduced; this preserves historical
analytical regression results and, more importantly, avoids silently assuming
one Annex-B climate-zone value.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

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


def _construction_inputs_are_explicit(opaque_elements, zone_id: str) -> bool:
    selected = [element for element in opaque_elements if element.zone_id == zone_id]
    return bool(selected) and all(
        getattr(element, "thermal_node_capacities_kj_m2k", None) is not None
        and getattr(element, "thermal_node_resistances_m2k_w", None) is not None
        for element in selected
    )


def solve_zone_iso52016(*args, **kwargs):
    require_nodes = bool(kwargs.get("require_explicit_construction_nodes", False))
    strict_raw = kwargs.get("strict_conformance", None)
    strict = bool(strict_raw) if strict_raw is not None else False
    opaque = kwargs.get("opaque_elements")
    zone_id = kwargs.get("zone_id")
    if opaque is None or zone_id is None:
        raise TypeError("solve_zone_iso52016 requires opaque_elements and zone_id as keyword arguments")

    if require_nodes and not _construction_inputs_are_explicit(opaque, zone_id):
        raise ValueError(
            "Explicit five-node construction data are required: provide "
            "thermal_node_capacities_kj_m2k and thermal_node_resistances_m2k_w "
            "for every opaque element in the zone."
        )

    # The core historically interpreted require_explicit_construction_nodes as
    # full strict mode. Keep the construction requirement above, then pass the
    # actual conformance intent separately.
    kwargs["require_explicit_construction_nodes"] = False
    kwargs["strict_conformance"] = strict

    # Never silently choose one Annex-B sky-air temperature difference in a
    # compatibility calculation. Strict mode requires an explicit value via the
    # normative settings before the call reaches here.
    if not strict:
        kwargs["sky_temperature_difference_k"] = 0.0

    result = _core_solve(*args, **kwargs)
    if require_nodes and not strict and _construction_inputs_are_explicit(opaque, zone_id):
        # This property denotes whether the *construction-node data* were
        # inferred. Surface-film compatibility is separately reported by the
        # conformance preflight and must not make this legacy field lie about
        # construction input provenance.
        result.used_inferred_construction = False
    return result


_core.solve_zone_iso52016 = solve_zone_iso52016
