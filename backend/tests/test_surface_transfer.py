"""Analytic regressions for dynamic surface heat-transfer correlations."""

from __future__ import annotations

import numpy as np
import pytest

from app.engine.surface_transfer import (
    exterior_convection_coefficient,
    forced_convection_coefficient,
    linearized_longwave_coefficient,
    natural_convection_coefficient,
    surface_kind_from_inclination,
    wind_direction_modifier,
)


def test_wall_free_convection_matches_reference_formula() -> None:
    coefficient = natural_convection_coefficient(8.0, "wall")
    assert float(coefficient) == pytest.approx(1.3 * 8.0**0.3333)


def test_floor_and_ceiling_reverse_stable_unstable_coefficients() -> None:
    floor_warm = float(natural_convection_coefficient(8.0, "floor"))
    floor_cold = float(natural_convection_coefficient(-8.0, "floor"))
    ceiling_warm = float(natural_convection_coefficient(8.0, "ceiling"))
    ceiling_cold = float(natural_convection_coefficient(-8.0, "ceiling"))

    assert floor_warm == pytest.approx(1.51 * 8.0**0.3333)
    assert floor_cold == pytest.approx(0.76 * 8.0**0.3333)
    assert ceiling_warm == pytest.approx(floor_cold)
    assert ceiling_cold == pytest.approx(floor_warm)


def test_wind_direction_modifier_distinguishes_windward_and_leeward() -> None:
    modifiers = wind_direction_modifier(180.0, np.array([180.0, 0.0, 270.0]))
    assert modifiers.tolist() == [1.0, 0.5, 1.0]


def test_forced_convection_matches_square_surface_reduction() -> None:
    coefficient = forced_convection_coefficient(
        area_m2=16.0,
        wind_speed_m_s=4.0,
        wind_direction_deg=180.0,
        surface_azimuth_deg=180.0,
        roughness="rough",
    )
    expected = 2.537 * 1.0 * 1.67 * 2.0 / 16.0**0.25 * 4.0**0.5
    assert float(coefficient) == pytest.approx(expected)


def test_non_wind_exposed_surface_uses_natural_convection_only() -> None:
    coefficient = exterior_convection_coefficient(
        delta_t_k=8.0,
        surface_kind="floor",
        area_m2=48.0,
        wind_speed_m_s=10.0,
        wind_direction_deg=180.0,
        surface_azimuth_deg=0.0,
        wind_exposed=False,
    )
    expected = natural_convection_coefficient(8.0, "floor")
    assert float(coefficient) == pytest.approx(float(expected))


def test_longwave_linearisation_is_positive_and_symmetric_in_temperatures() -> None:
    forward = float(linearized_longwave_coefficient(20.0, 0.0, emissivity=0.9))
    reverse = float(linearized_longwave_coefficient(0.0, 20.0, emissivity=0.9))
    assert forward > 0.0
    assert forward == pytest.approx(reverse)


def test_surface_kind_from_project_inclination() -> None:
    assert surface_kind_from_inclination(0.0) == "ceiling"
    assert surface_kind_from_inclination(90.0) == "wall"
    assert surface_kind_from_inclination(180.0) == "floor"
