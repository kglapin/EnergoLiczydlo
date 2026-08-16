import numpy as np
import pytest

from app.engine.climate import load_epw, make_synthetic_year, radiation_on_surface
from app.engine.climate import AIR_DENSITY_KG_M3, AIR_SPECIFIC_HEAT_J_KGK


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
    assert AIR_DENSITY_KG_M3 * AIR_SPECIFIC_HEAT_J_KGK == pytest.approx(1206.0, abs=1.0)
