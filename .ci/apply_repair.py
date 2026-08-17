from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if old not in text:
        status = "already applied" if new in text else "pattern not present"
        print(f"SKIP {path}: {status}")
        return
    target.write_text(text.replace(old, new), encoding="utf-8")


# ISO 52016 hourly core: preserve U-value exactly in compatibility mode,
# keep strict mode dependent on explicit convective/radiative coefficients,
# validate ventilation, and make mypy understand window/bridge branches.
replace(
    "backend/app/engine/iso52016_hourly.py",
    "        result = Film(*(float(value) for value in values))\n",
    "        numeric = [float(cast(float, value)) for value in values]\n"
    "        result = Film(numeric[0], numeric[1], numeric[2], numeric[3])\n",
)
replace(
    "backend/app/engine/iso52016_hourly.py",
    "    h_ri = min(5.0, max(h_i - 0.1, 0.0))\n"
    "    return Film(max(h_i - h_ri, 0.1), h_ri, 20.0, 5.0, True)\n",
    "    # Compatibility input provides only U. Do not invent a separate\n"
    "    # long-wave room network because that would change the stated U-value\n"
    "    # in degenerate analytical cases. Strict mode requires h_ci/h_ri.\n"
    "    return Film(h_i, 0.0, 25.0, 0.0, True)\n",
)
replace(
    "backend/app/engine/iso52016_hourly.py",
    "        host = opaque.get(getattr(bridge, \"element_id\", None))\n",
    "        host_id = getattr(bridge, \"element_id\", None)\n"
    "        host = opaque.get(host_id) if isinstance(host_id, str) else None\n",
)
replace(
    "backend/app/engine/iso52016_hourly.py",
    "        for path in prepared.windows:\n"
    "            rhs[path.indices[0]] += path.h_boundary * path.boundary[hour]\n",
    "        for window_path in prepared.windows:\n"
    "            rhs[window_path.indices[0]] += (\n"
    "                window_path.h_boundary * window_path.boundary[hour]\n"
    "            )\n",
)
replace(
    "backend/app/engine/iso52016_hourly.py",
    "        for path in prepared.windows:\n"
    "            outward += path.h_boundary * (current[path.indices[0]] - path.boundary[hour])\n"
    "            window_history[path.element.id][hour, :] = current[list(path.indices)]\n",
    "        for window_path in prepared.windows:\n"
    "            outward += window_path.h_boundary * (\n"
    "                current[window_path.indices[0]] - window_path.boundary[hour]\n"
    "            )\n"
    "            window_history[window_path.element.id][hour, :] = current[\n"
    "                list(window_path.indices)\n"
    "            ]\n",
)
replace(
    "backend/app/engine/iso52016_hourly.py",
    "    ventilation = _hourly(h_ve, n, \"h_ve\"); supply = outdoor if t_supply is None else _hourly(t_supply, n, \"t_supply\")\n",
    "    ventilation = _hourly(h_ve, n, \"h_ve\")\n"
    "    if np.any(ventilation < 0.0):\n"
    "        raise ValueError(\"h_ve must be non-negative\")\n"
    "    supply = outdoor if t_supply is None else _hourly(t_supply, n, \"t_supply\")\n",
)
replace(
    "backend/app/engine/iso52016_hourly.py",
    "    size = prepared.matrix.shape[0]\n",
    "",
)

# Compatibility façade already selects an air-temperature thermostat in
# non-strict mode; normalize the validation message for the regression test.
replace(
    "backend/app/engine/iso52016_hourly/__init__.py",
    "            \"Explicit five-node construction data are required: provide \"\n",
    "            \"explicit five-node construction data are required: provide \"\n",
)

# Extended schema: expose the inherited enum explicitly for static analysis.
replace(
    "backend/app/schemas/models/__init__.py",
    "for _name in dir(_legacy):\n"
    "    if not _name.startswith(\"__\"):\n"
    "        globals()[_name] = getattr(_legacy, _name)\n\n",
    "for _name in dir(_legacy):\n"
    "    if not _name.startswith(\"__\"):\n"
    "        globals()[_name] = getattr(_legacy, _name)\n\n"
    "AdjacentSpaceType = _legacy.AdjacentSpaceType\n\n",
)

# Monthly numerical functions: typed ndarray helper removes Any leakage from NumPy.
replace(
    "backend/app/engine/iso52016_monthly.py",
    "from dataclasses import dataclass\n\nimport numpy as np\n",
    "from dataclasses import dataclass\n"
    "from typing import TypeAlias, cast\n\n"
    "import numpy as np\n"
    "from numpy.typing import NDArray\n\n"
    "FloatArray: TypeAlias = NDArray[np.float64]\n\n\n"
    "def _arr(value: object) -> FloatArray:\n"
    "    return cast(FloatArray, np.asarray(value, dtype=np.float64))\n",
)
monthly = ROOT / "backend/app/engine/iso52016_monthly.py"
text = monthly.read_text(encoding="utf-8").replace("np.ndarray", "FloatArray")
text = text.replace(
    "return np.asarray(effective_internal_capacity_j_k / (3600.0 * h_total), dtype=float)",
    "return _arr(effective_internal_capacity_j_k / (3600.0 * h_total))",
)
text = text.replace(
    "return np.asarray(a0 + np.asarray(tau_h, dtype=float) / tau0_h, dtype=float)",
    "return _arr(a0 + _arr(tau_h) / tau0_h)",
)
text = text.replace(
    "return np.asarray(np.clip(result, 0.0, 1.0), dtype=float)",
    "return _arr(np.clip(result, 0.0, 1.0))",
)
text = text.replace("result = np.asarray(values, dtype=float)", "result = _arr(values)")
text = text.replace(
    "heating = np.maximum(h_transfer - eta_h * h_gains, 0.0)",
    "heating = _arr(np.maximum(h_transfer - eta_h * h_gains, 0.0))",
)
text = text.replace(
    "cooling = np.maximum(c_gains - eta_c * c_transfer, 0.0)",
    "cooling = _arr(np.maximum(c_gains - eta_c * c_transfer, 0.0))",
)
monthly.write_text(text, encoding="utf-8")

# Design load: typed ndarray helper and explicit local annotations.
replace(
    "backend/app/engine/iso52016_design_load.py",
    "from math import ceil\n\nimport numpy as np\n",
    "from math import ceil\n"
    "from typing import TypeAlias, cast\n\n"
    "import numpy as np\n"
    "from numpy.typing import NDArray\n",
)
replace(
    "backend/app/engine/iso52016_design_load.py",
    "from app.schemas.models import AdjacentSpaceType, BuildingProject\n",
    "from app.schemas.models import BuildingProject\n\n"
    "FloatArray: TypeAlias = NDArray[np.float64]\n\n\n"
    "def _arr(value: object) -> FloatArray:\n"
    "    return cast(FloatArray, np.asarray(value, dtype=np.float64))\n",
)
design = ROOT / "backend/app/engine/iso52016_design_load.py"
text = design.read_text(encoding="utf-8").replace("np.ndarray", "FloatArray")
text = text.replace(
    "return np.tile(np.asarray(values, dtype=float), repetitions)",
    "return _arr(np.tile(_arr(values), repetitions))",
)
text = text.replace(
    "extract_base = np.full(n, float(zone.setpoint_heating), dtype=float)",
    "extract_base: FloatArray = _arr(np.full(n, float(zone.setpoint_heating)))",
)
text = text.replace(
    "zeros = np.zeros(n, dtype=float)",
    "zeros: FloatArray = _arr(np.zeros(n))",
)
text = text.replace(
    "heating_sum = np.sum([item.heating_w for item in zone_results], axis=0)",
    "heating_sum = _arr(np.sum([item.heating_w for item in zone_results], axis=0))",
)
text = text.replace(
    "cooling_sum = np.sum([item.cooling_w for item in zone_results], axis=0)",
    "cooling_sum = _arr(np.sum([item.cooling_w for item in zone_results], axis=0))",
)
design.write_text(text, encoding="utf-8")

# Post-repair conservation test must include the newly normative dynamic
# air/furniture storage term, not only construction storage.
replace(
    "backend/tests/test_post_repair_audit.py",
    "        require_explicit_construction_nodes=True,\n"
    "    )\n"
    "    capacities = np.asarray([40.0] * 5) * 25.0 * 1000.0\n"
    "    nodes = solution.construction_node_temperatures[\"wall\"]\n"
    "    previous = np.vstack([np.full((1, 5), 20.0), nodes[:-1]])\n"
    "    storage_w = np.sum(capacities * (nodes - previous), axis=1) / 3600.0\n",
    "        require_explicit_construction_nodes=True,\n"
    "        air_furniture_heat_capacity_j_k=100_000.0,\n"
    "    )\n"
    "    capacities = np.asarray([40.0] * 5) * 25.0 * 1000.0\n"
    "    nodes = solution.construction_node_temperatures[\"wall\"]\n"
    "    previous = np.vstack([np.full((1, 5), 20.0), nodes[:-1]])\n"
    "    construction_storage_w = (\n"
    "        np.sum(capacities * (nodes - previous), axis=1) / 3600.0\n"
    "    )\n"
    "    previous_air = np.concatenate(([20.0], solution.t_air[:-1]))\n"
    "    air_storage_w = (\n"
    "        100_000.0 * (solution.t_air - previous_air) / 3600.0\n"
    "    )\n"
    "    storage_w = construction_storage_w + air_storage_w\n",
)

print("Deterministic repair patch applied")
