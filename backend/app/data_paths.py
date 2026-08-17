"""Filesystem paths shared by the calculation engine and API."""

from __future__ import annotations

import os
from pathlib import Path


def resolve_tmy_data_dir(module_file: str | Path) -> Path:
    """Resolve the directory containing bundled TMY/EPW files.

    ``TMY_DATA_PATH`` has priority, which is useful for local and hosted
    deployments. Without it, both the repository layout (``data/tmy`` next
    to ``backend``) and the packaged layout (``data/tmy`` next to ``app``)
    are supported.
    """

    configured = os.environ.get("TMY_DATA_PATH")
    if configured:
        return Path(configured)

    module_path = Path(module_file)
    candidates = (
        module_path.parents[3] / "data" / "tmy",
        module_path.parents[2] / "data" / "tmy",
        Path.cwd() / "data" / "tmy",
    )
    return next((candidate for candidate in candidates if candidate.is_dir()), candidates[0])
