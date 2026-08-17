import numpy as np
import pytest

from app.engine.envelope import (
    adjacent_temperature,
    compute_opaque_heat_loss,
    compute_thermal_bridge_loss,
    total_transmission_coefficient,
)
from app.schemas.models import (
    AdjacentSpaceType,
    ElementType,
    LinearThermalBridge,
    OpaqueElement,
    PointThermalBridge,
    ThermalBridgeConfig,
    ThermalZone,
)


def test_opaque_heat_loss_outdoor():
    wall = OpaqueElement(
        id="wall",
        name="wall",
        zone_id="z1",
        element_type=ElementType.EXTERNAL_WALL,
        orientation_azimuth=0.0,
        inclination=90.0,
        area=10.0,
        u_value=0.2,
        adjacent_space_type=AdjacentSpaceType.OUTDOOR,
    )
    T_int = np.full(8760, 20.0)
    T_e = np.full(8760, 0.0)
    loss = compute_opaque_heat_loss(wall, T_int, T_e)
    expected = 10.0 * 0.2 * 20.0
    np.testing.assert_allclose(loss, expected)


def test_adjacent_temperature_ground():
    floor = OpaqueElement(
        id="floor",
        name="floor",
        zone_id="z1",
        element_type=ElementType.GROUND_FLOOR,
        orientation_azimuth=0.0,
        inclination=180.0,
        area=20.0,
        u_value=0.25,
        adjacent_space_type=AdjacentSpaceType.GROUND,
    )
    T_e = np.full(8760, 0.0)
    T_adj = adjacent_temperature(floor, T_e)
    assert np.isfinite(T_adj).all()
    # Ground temperature should be less variable than outdoor temperature
    assert T_adj.std() < 10.0


def test_thermal_bridge_loss():
    zone = ThermalZone(id="z1", name="z1", zone_type="heated", floor_area=50.0, volume=125.0)
    bridges = ThermalBridgeConfig(
        linear_bridges=[
            LinearThermalBridge(id="lb1", name="lb1", psi_value=0.05, length=20.0, zone_id="z1")
        ],
        point_bridges=[
            PointThermalBridge(id="pb1", name="pb1", chi_value=0.5, count=4, zone_id="z1")
        ],
    )
    T_int = np.full(8760, 20.0)
    T_e = np.full(8760, 0.0)
    loss = compute_thermal_bridge_loss(bridges, zone, T_int, T_e)
    expected = (0.05 * 20.0 + 0.5 * 4) * 20.0
    np.testing.assert_allclose(loss, expected)


def test_total_transmission_coefficient():
    opaque = [
        OpaqueElement(
            id="w1",
            name="w1",
            zone_id="z1",
            element_type=ElementType.EXTERNAL_WALL,
            orientation_azimuth=0.0,
            inclination=90.0,
            area=10.0,
            u_value=0.2,
        )
    ]
    bridges = ThermalBridgeConfig(
        linear_bridges=[
            LinearThermalBridge(id="lb1", name="lb1", psi_value=0.05, length=10.0, zone_id="z1")
        ]
    )
    H = total_transmission_coefficient(opaque, [], bridges)
    assert pytest.approx(10.0 * 0.2 + 0.05 * 10.0) == H
