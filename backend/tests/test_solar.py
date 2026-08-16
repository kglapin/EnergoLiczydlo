import numpy as np

from app.engine.climate import make_synthetic_year, radiation_on_surface
from app.engine.solar import solar_gains_transparent
from app.schemas.models import TransparentElement


def test_solar_gains_transparent_south():
    df = make_synthetic_year(
        GHI=500.0,
        DNI=300.0,
        DHI=200.0,
        latitude=52.0,
        longitude=21.0,
        elevation=100.0,
    )
    window = TransparentElement(
        id="win",
        name="Okno południowe",
        zone_id="z1",
        element_type="window",
        orientation_azimuth=180.0,
        inclination=90.0,
        area=2.0,
        u_value=1.0,
        g_value=0.6,
        frame_factor=0.2,
        shading_factor=1.0,
    )
    gains = solar_gains_transparent(window, df)
    assert len(gains) == 8760
    assert np.isfinite(gains).all()
    assert (gains >= 0).all()
    # Net area = 2.0 * 0.8 = 1.6 m2; max irradiance should not exceed gross area * I
    max_gain = np.max(gains)
    max_irradiance = np.max(radiation_on_surface(df, 90.0, 180.0))
    assert max_gain <= 1.6 * max_irradiance * window.g_value * 1.001
