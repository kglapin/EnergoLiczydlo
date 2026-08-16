import numpy as np

from app.engine.thermal_balance import solve_hourly_balance


def test_no_load_at_setpoint_with_zero_gains():
    """With T_e = T_set_heating and no gains/losses, no heating/cooling needed."""
    n = 8760
    T_e = np.full(n, 20.0)
    Q_int = np.zeros(n)
    Q_sol = np.zeros(n)
    T_int, Q_H, Q_C, _ = solve_hourly_balance(
        H_tr=50.0,
        H_ve=30.0,
        Q_int=Q_int,
        Q_sol=Q_sol,
        T_e=T_e,
        T_set_heating=20.0,
        T_set_cooling=26.0,
        C_m=3000.0,
    )
    assert np.sum(Q_H) == 0.0
    assert np.sum(Q_C) == 0.0
    np.testing.assert_allclose(T_int, 20.0, atol=1e-6)


def test_heating_demand_when_cold():
    """Constant cold outdoor temperature should produce heating demand."""
    n = 8760
    T_e = np.full(n, -10.0)
    Q_int = np.zeros(n)
    Q_sol = np.zeros(n)
    _, Q_H, Q_C, _ = solve_hourly_balance(
        H_tr=50.0,
        H_ve=30.0,
        Q_int=Q_int,
        Q_sol=Q_sol,
        T_e=T_e,
        T_set_heating=20.0,
        T_set_cooling=None,
        C_m=3000.0,
    )
    assert np.sum(Q_H) > 0.0
    assert np.sum(Q_C) == 0.0


def test_cooling_demand_when_hot():
    """Constant hot outdoor temperature with solar gains should produce cooling."""
    n = 8760
    T_e = np.full(n, 30.0)
    Q_int = np.full(n, 500.0)
    Q_sol = np.full(n, 1000.0)
    _, Q_H, Q_C, _ = solve_hourly_balance(
        H_tr=50.0,
        H_ve=30.0,
        Q_int=Q_int,
        Q_sol=Q_sol,
        T_e=T_e,
        T_set_heating=20.0,
        T_set_cooling=26.0,
        C_m=3000.0,
    )
    assert np.sum(Q_C) > 0.0
