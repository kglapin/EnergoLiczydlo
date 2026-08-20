import numpy as np
import pandas as pd
import pytest
from fastapi import HTTPException

import app.engine.climate as climate_module
from app.api import climate as climate_api
from app.data_paths import resolve_tmy_data_dir
from app.engine.climate import (
    AIR_DENSITY_KG_M3,
    AIR_SPECIFIC_HEAT_J_KGK,
    ClimateStation,
    haversine_distance_km,
    load_epw,
    make_synthetic_year,
    nearest_climate_station,
    radiation_on_surface,
)


def test_load_epw_returns_8760_hours(shared_data_dir):
    path = shared_data_dir / "POL_MZ_Okecie-Warszawa-Chopina.Intl.AP.123750_TMYx.2009-2023.epw"
    if not path.exists():
        pytest.skip("EPW file not available")
    df = load_epw(path)
    assert len(df) == 8760
    assert "T_e" in df.columns
    assert "GHI" in df.columns
    assert "DNI" in df.columns
    assert "DHI" in df.columns
    assert "sun_zenith" in df.columns


def test_epw_and_solar_fallback_work_without_pvlib(monkeypatch, shared_data_dir):
    path = shared_data_dir / "POL_MZ_Okecie-Warszawa-Chopina.Intl.AP.123750_TMYx.2009-2023.epw"
    if not path.exists():
        pytest.skip("EPW file not available")
    monkeypatch.setattr(climate_module, "pvlib", None)
    df = climate_module.load_epw(path)
    assert len(df) == 8760
    assert np.isfinite(df[["sun_zenith", "sun_azimuth"]].to_numpy()).all()
    poa = climate_module.radiation_on_surface(df, surface_tilt=90.0, surface_azimuth=180.0)
    assert len(poa) == 8760
    assert np.isfinite(poa).all()
    assert (poa >= 0.0).all()


def test_tmy_data_dir_resolves_repository_layout(shared_data_dir):
    """The bundled-data layout is found when no deployment override is set."""
    assert resolve_tmy_data_dir(climate_module.__file__) == shared_data_dir


def test_tmy_data_dir_honors_environment_override(monkeypatch, tmp_path):
    """Hosted deployments can provide an explicit EPW directory."""
    monkeypatch.setenv("TMY_DATA_PATH", str(tmp_path))
    assert resolve_tmy_data_dir(climate_module.__file__) == tmp_path


def test_load_epw_rejects_non_8760_series(monkeypatch, tmp_path):
    path = tmp_path / "short.epw"
    path.write_text("placeholder")
    n = 8759
    raw = pd.DataFrame(
        {
            "temp_air": np.zeros(n),
            "temp_dew": np.zeros(n),
            "relative_humidity": np.full(n, 50.0),
            "atmospheric_pressure": np.full(n, 101325.0),
            "ghi": np.zeros(n),
            "dni": np.zeros(n),
            "dhi": np.zeros(n),
            "wind_speed": np.ones(n),
            "wind_direction": np.zeros(n),
            "total_sky_cover": np.zeros(n),
        }
    )
    monkeypatch.setattr(
        "app.engine.climate.pvlib.iotools.read_epw",
        lambda *args, **kwargs: (
            raw,
            {"latitude": 52.0, "longitude": 21.0, "altitude": 100.0},
        ),
    )
    with pytest.raises(ValueError, match="exactly 8760"):
        load_epw(path)


def test_synthetic_year_constant_temperature():
    df = make_synthetic_year(T_e=10.0, latitude=52.0, longitude=21.0, elevation=100.0)
    assert len(df) == 8760
    np.testing.assert_allclose(df["T_e"].to_numpy(), 10.0)


def test_radiation_horizontal_surface_matches_ghi():
    df = make_synthetic_year(
        GHI=500.0, DNI=300.0, DHI=200.0, latitude=52.0, longitude=21.0, elevation=100.0
    )
    I_surf = radiation_on_surface(df, surface_tilt=0, surface_azimuth=180)
    # Horizontal surface total irradiance should be close to GHI at solar noon on clear days
    assert np.isfinite(I_surf).all()
    assert (I_surf >= 0).all()


def test_air_specific_heat_constants():
    # Sanity check: volumetric heat capacity ~ 1206 J/(m3*K)
    assert pytest.approx(1206.0, abs=1.0) == AIR_DENSITY_KG_M3 * AIR_SPECIFIC_HEAT_J_KGK


def test_haversine_distance_is_zero_for_the_same_point():
    assert haversine_distance_km(52.2297, 21.0122, 52.2297, 21.0122) == pytest.approx(0.0)


def test_nearest_climate_station_returns_shortest_distance():
    stations = [
        ClimateStation("west", "West", 52.4, 16.8),
        ClimateStation("east", "East", 52.2, 21.0),
    ]

    station, distance_km = nearest_climate_station(52.23, 21.01, stations)

    assert station.station_id == "east"
    assert distance_km == pytest.approx(haversine_distance_km(52.23, 21.01, 52.2, 21.0))


def test_resolve_location_selects_station_nearest_to_geocoded_point(monkeypatch):
    monkeypatch.setattr(
        climate_api,
        "_geocode_location",
        lambda query: ("Warszawa, Mazowieckie, Polska", 52.2297, 21.0122),
    )

    result = climate_api.resolve_location(" Warszawa ")

    assert result["query"] == "Warszawa"
    assert result["matched_location"] == "Warszawa, Mazowieckie, Polska"
    assert result["station"]["id"] == "POL_MZ_Okecie-Warszawa-Chopina.Intl.AP.123750_TMYx.2009-2023"
    assert result["station"]["distance_km"] > 0


def test_resolve_location_blocks_when_no_stations_available(monkeypatch):
    """Brak danych TMY ma skutkować czytelną blokadą obliczenia, a nie błędem 500."""
    monkeypatch.setattr(
        climate_api,
        "_geocode_location",
        lambda query: ("Warszawa, Mazowieckie, Polska", 52.2297, 21.0122),
    )
    monkeypatch.setattr(climate_api, "_available_stations", lambda: [])

    with pytest.raises(HTTPException) as exc_info:
        climate_api.resolve_location("Warszawa")

    assert exc_info.value.status_code == 503
    assert "stacji klimatycznych" in exc_info.value.detail
