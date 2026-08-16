from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def project_root() -> Path:
    return Path(__file__).parents[3]


@pytest.fixture(scope="session")
def shared_data_dir(project_root: Path) -> Path:
    return project_root / "data" / "tmy"
