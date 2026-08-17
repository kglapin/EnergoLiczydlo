"""Dodatkowy raport liczbowy BESTEST Case 600 dla pełnego audytu technicznego."""

from __future__ import annotations

import os

import pytest

from tests.test_external_bestest import (
    CASE_600_REFERENCE,
    _bestest_case_600_solution,
    _download_bestest_weather,
)


@pytest.mark.skipif(
    os.environ.get("RUN_EXTERNAL_BENCHMARKS") != "1",
    reason="ustaw RUN_EXTERNAL_BENCHMARKS=1, aby pobrać publiczny plik pogodowy BESTEST",
)
def test_report_exact_bestest_case_600_values(tmp_path) -> None:
    epw_path = tmp_path / "DRYCOLDTMY.epw"
    _download_bestest_weather(epw_path)
    solution = _bestest_case_600_solution(epw_path, integrated_g_value=0.68)
    actual = {
        "annual_heating_kwh": float(solution.q_heating.sum()) / 1000.0,
        "annual_cooling_kwh": float(solution.q_cooling.sum()) / 1000.0,
        "peak_heating_w": float(solution.q_heating.max()),
        "peak_cooling_w": float(solution.q_cooling.max()),
    }
    print("AUDYT_BESTEST_CASE_600=", actual)
    print("AUDYT_BESTEST_REFERENCE=", CASE_600_REFERENCE)
    assert CASE_600_REFERENCE["annual_heating_kwh"][0] <= actual["annual_heating_kwh"] <= CASE_600_REFERENCE["annual_heating_kwh"][1]
    assert CASE_600_REFERENCE["annual_cooling_kwh"][0] <= actual["annual_cooling_kwh"] <= CASE_600_REFERENCE["annual_cooling_kwh"][1]
    assert CASE_600_REFERENCE["peak_heating_w"][0] <= actual["peak_heating_w"] <= CASE_600_REFERENCE["peak_heating_w"][1]
    assert CASE_600_REFERENCE["peak_cooling_w"][0] <= actual["peak_cooling_w"] <= CASE_600_REFERENCE["peak_cooling_w"][1]
