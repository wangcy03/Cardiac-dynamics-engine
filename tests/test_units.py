"""Dimensioned SI interface conversions and exact scheduling seam."""
import math

import pytest

from iabp.units import (
    m3_s_to_ml_s, m3_to_ml, ml_s_to_m3_s, ml_to_m3, mmhg_to_pa, pa_to_mmhg,
    s_to_us_exact, us_to_s,
)


def test_pressure_volume_and_flow_conversion_roundtrips() -> None:
    assert mmhg_to_pa(1.0) == 133.322387415
    assert pa_to_mmhg(133.322387415) == 1.0
    assert m3_to_ml(1.0) == 1_000_000.0
    assert ml_to_m3(1.0) == 1e-6
    assert m3_s_to_ml_s(2e-6) == 2.0
    assert ml_s_to_m3_s(2.0) == 2e-6
    for value in (-100.0, 0.0, 70.0, 1234.0):
        assert pa_to_mmhg(mmhg_to_pa(value)) == pytest.approx(value, rel=2e-16)
        assert m3_to_ml(ml_to_m3(value)) == pytest.approx(value, rel=2e-16)


@pytest.mark.parametrize("value", [math.inf, -math.inf, math.nan])
def test_nonfinite_unit_inputs_are_rejected(value: float) -> None:
    for conversion in (mmhg_to_pa, pa_to_mmhg, m3_to_ml, ml_to_m3, s_to_us_exact):
        with pytest.raises(ValueError):
            conversion(value)


def test_integer_microsecond_time_seam_never_silently_rounds() -> None:
    assert us_to_s(250) == 0.00025
    assert s_to_us_exact(0.00025) == 250
    assert s_to_us_exact(us_to_s(1234567)) == 1234567
    with pytest.raises(ValueError, match="representable"):
        s_to_us_exact(0.0002501)
    with pytest.raises(ValueError, match="integer"):
        us_to_s(1.5)


@pytest.mark.parametrize("value", [1e308, -1e308])
def test_finite_input_that_overflows_conversion_is_rejected(value: float) -> None:
    for conversion in (mmhg_to_pa, m3_to_ml, m3_s_to_ml_s, s_to_us_exact):
        with pytest.raises(ValueError, match="finite"):
            conversion(value)
