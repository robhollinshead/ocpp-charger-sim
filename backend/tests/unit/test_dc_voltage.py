"""Unit tests: dc_voltage (sigmoid OCV model for DC pack voltage)."""
import pytest

from simulator_core.dc_voltage import DEFAULT_CELLS, get_pack_voltage_V, ocv_from_soc

pytestmark = pytest.mark.unit


def test_ocv_from_soc_zero():
    """At 0% SOC, cell voltage reflects the sigmoid plateau (~3.9V)."""
    voltage = ocv_from_soc(0.0)
    assert 3.85 <= voltage <= 3.95


def test_ocv_from_soc_full():
    """At 100% SOC, cell voltage is near Vmax (~4.15V)."""
    voltage = ocv_from_soc(1.0)
    assert 4.1 <= voltage <= 4.2


def test_ocv_from_soc_mid():
    """At 50% SOC, cell voltage is at the sigmoid midpoint (~4.025V)."""
    voltage = ocv_from_soc(0.5)
    assert 4.0 <= voltage <= 4.1


def test_ocv_increases_with_soc():
    """OCV increases monotonically with SOC."""
    soc_values = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
    voltages = [ocv_from_soc(soc) for soc in soc_values]
    for i in range(1, len(voltages)):
        assert voltages[i] > voltages[i - 1]


def test_get_pack_voltage_V_default_cells():
    """get_pack_voltage_V uses 108 cells by default."""
    assert DEFAULT_CELLS == 108
    pack_voltage = get_pack_voltage_V(50.0)
    cell_voltage = ocv_from_soc(0.5)
    assert abs(pack_voltage - cell_voltage * 108) < 0.01


def test_get_pack_voltage_V_custom_cells():
    """get_pack_voltage_V can use custom cell count."""
    pack_voltage = get_pack_voltage_V(50.0, cells=96)
    cell_voltage = ocv_from_soc(0.5)
    assert abs(pack_voltage - cell_voltage * 96) < 0.01


def test_get_pack_voltage_V_at_20_soc():
    """At 20% SOC with 108 cells, pack voltage is in expected range (~420V)."""
    pack_voltage = get_pack_voltage_V(20.0)
    assert 415 < pack_voltage < 430


def test_get_pack_voltage_V_at_80_soc():
    """At 80% SOC with 108 cells, pack voltage is in expected range (~430V)."""
    pack_voltage = get_pack_voltage_V(80.0)
    assert 420 < pack_voltage < 450


def test_get_pack_voltage_V_clamps_soc():
    """SOC outside 0-100 is clamped."""
    low = get_pack_voltage_V(-10.0)
    zero = get_pack_voltage_V(0.0)
    assert abs(low - zero) < 0.01

    high = get_pack_voltage_V(110.0)
    hundred = get_pack_voltage_V(100.0)
    assert abs(high - hundred) < 0.01
