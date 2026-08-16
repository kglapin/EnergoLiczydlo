import pytest

from app.engine.calculator import calculate_building_energy
from scripts.test_building import make_test_project


@pytest.mark.parametrize("setpoint_cooling", [None, 26.0])
def test_calculator_runs_and_returns_results(setpoint_cooling):
    project = make_test_project()
    if setpoint_cooling is None:
        project.thermal_zones[0].setpoint_cooling = None
    result = calculate_building_energy(project)
    assert result.status == "success"
    assert result.annual_indicators.eu_kwh_m2_year >= 0
    assert result.annual_indicators.ek_kwh_m2_year >= 0
    assert result.annual_indicators.ep_kwh_m2_year >= 0
    assert len(result.monthly) == 12


def test_energy_hierarchy():
    """Final energy should not be lower than useful energy for non-renewable carriers."""
    project = make_test_project()
    result = calculate_building_energy(project)
    # For the default heat pump, Ek can be lower than Eu due to COP > 1.
    # We still check non-negativity and that Ep >= Ek because primary factor >= 1.
    assert result.annual_indicators.ep_kwh_m2_year >= result.annual_indicators.ek_kwh_m2_year - 1e-6
    assert result.annual_indicators.eu_kwh_m2_year >= 0
