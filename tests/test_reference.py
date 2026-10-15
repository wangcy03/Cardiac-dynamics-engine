"""Independent SciPy integration of the SAME 0D equations, not biological validation."""
import numpy as np
from scipy.integrate import solve_ivp
from iabp.model import Model

def independent_rhs(t, y):
    v = y[:9]
    q = y[9:14]
    z = y[14:18]
    a = y[18:20]
    c = y[20:22]
    target = np.array([0.0, 0.9 if t < 0.2 else 0.0])
    tau = np.where(target > c, 0.05, 0.035)
    p = np.array([0.05 * (v[0] - 10) + 0.12 * np.expm1(0.022 * (v[0] - 10)) + 2.1 * a[1] * (v[0] - 10), (v[1] - 50) / 0.22, (v[2] - 75) / 0.85, (v[3] - 2600) / 80, (0.1 + 0.25 * a[0]) * (v[4] - 20), 0.025 * (v[5] - 15) + 0.04 * np.expm1(0.018 * (v[5] - 15)) + 0.5 * a[1] * (v[5] - 15), (v[6] - 80) / 5, (v[7] - 320) / 20, (0.16 + 0.35 * a[0]) * (v[8] - 20)])
    edges = [(8, 0), (0, 1), (1, 2), (4, 5), (5, 6)]
    ro = np.array([0.012, 0.035, 0.009, 0.012])
    rv = ro + (20 - ro) * (1 - z) ** 4
    r = np.array([rv[0], rv[1], 0.08, rv[2], rv[3]])
    dp = np.array([p[i] - p[k] for i, k in edges])
    dq = (dp - r * q) / np.array([0.0002, 0.0004, 0.0007, 0.0002, 0.00015])
    dv = np.zeros(9)
    for j, (i, k) in enumerate(edges):
        dv[i] -= q[j]
        dv[k] += q[j]
    for (i, k), res in zip([(2, 3), (3, 4), (6, 7), (7, 8)], [1.1, 0.02, 0.09, 0.02]):
        x = (p[i] - p[k]) / res
        dv[i] -= x
        dv[k] += x
    dz = 7 * np.maximum(dp[[0, 1, 3, 4]], 0) * (1 - z) - 12 * np.maximum(-dp[[0, 1, 3, 4]], 0) * z
    return np.concatenate([dv, dq, dz, (c - a) / tau, (target - c) / tau])

def test_against_independent_radau():
    m = Model()
    y0 = np.array(m.state.volumes + m.state.flows + m.state.gates + m.state.activation + m.state.calcium_proxy)
    first = solve_ivp(independent_rhs, [0, 0.2], y0, method='Radau', rtol=1e-09, atol=1e-10, max_step=0.001)
    second = solve_ivp(independent_rhs, [0.2, 0.5], first.y[:, -1], method='Radau', rtol=1e-09, atol=1e-10, max_step=0.001)
    assert first.success and second.success
    for i in range(10000):
        m.targets[1] = 0.9 if i < 4000 else 0
        m.advance(5e-05)
    actual = np.array(m.state.volumes + m.state.flows + m.state.gates + m.state.activation + m.state.calcium_proxy)
    assert np.max(abs(actual[:9] - second.y[:9, -1])) < 0.02
    assert np.max(abs(actual[9:14] - second.y[9:14, -1])) < 0.1
    assert np.max(abs(actual[14:] - second.y[14:, -1])) < 0.002
