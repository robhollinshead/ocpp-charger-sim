"""Unit tests for AC charger support."""
import math

import pytest

from simulator_core.charger import Charger
from simulator_core.evse import EVSE, EvseState, AC_GRID_VOLTAGE_V, SQRT3


pytestmark = pytest.mark.unit


class TestChargerPowerType:
    """Tests for charger power_type field."""

    def test_default_power_type_is_dc(self):
        """Default power_type should be DC."""
        charger = Charger(charge_point_id="CP001")
        assert charger.power_type == "DC"

    def test_power_type_can_be_set_to_ac(self):
        """Power type can be set to AC at creation."""
        charger = Charger(charge_point_id="CP001", power_type="AC")
        assert charger.power_type == "AC"

    def test_power_type_propagates_to_evses(self):
        """Power type should propagate to EVSEs."""
        evses = [EVSE(evse_id=1), EVSE(evse_id=2)]
        charger = Charger(charge_point_id="CP001", evses=evses, power_type="AC")
        for evse in charger.evses:
            assert evse.power_type == "AC"


class TestEvsePowerType:
    """Tests for EVSE power_type field."""

    def test_default_power_type_is_dc(self):
        """Default EVSE power_type should be DC."""
        evse = EVSE(evse_id=1)
        assert evse.power_type == "DC"

    def test_power_type_can_be_set_to_ac(self):
        """EVSE power_type can be set to AC at creation."""
        evse = EVSE(evse_id=1, power_type="AC")
        assert evse.power_type == "AC"


class TestAcVoltageCalculation:
    """Tests for AC voltage calculations."""

    def test_ac_evse_returns_fixed_grid_voltage(self):
        """AC EVSE should return fixed 400V regardless of SoC."""
        evse = EVSE(evse_id=1, power_type="AC")
        evse.soc_pct = 20.0
        assert evse.get_voltage_V() == AC_GRID_VOLTAGE_V
        evse.soc_pct = 50.0
        assert evse.get_voltage_V() == AC_GRID_VOLTAGE_V
        evse.soc_pct = 80.0
        assert evse.get_voltage_V() == AC_GRID_VOLTAGE_V

    def test_dc_evse_returns_variable_voltage(self):
        """DC EVSE should return voltage based on SoC."""
        evse = EVSE(evse_id=1, power_type="DC")
        evse.soc_pct = 20.0
        v20 = evse.get_voltage_V()
        evse.soc_pct = 80.0
        v80 = evse.get_voltage_V()
        assert v80 > v20  # Higher SoC = higher voltage for Li-ion


class TestAcPowerConversion:
    """Tests for AC 3-phase power/current conversion."""

    def test_ac_current_to_power(self):
        """Convert current to power using 3-phase formula: P = sqrt(3) * V * I."""
        evse = EVSE(evse_id=1, power_type="AC")
        # 32A at 400V 3-phase
        power = evse.ac_current_to_power_W(32.0)
        expected = math.sqrt(3) * 400.0 * 32.0  # ~22.17 kW
        assert abs(power - expected) < 0.01

    def test_ac_power_to_current(self):
        """Convert power to current using 3-phase formula: I = P / (sqrt(3) * V)."""
        evse = EVSE(evse_id=1, power_type="AC")
        # 22 kW at 400V 3-phase
        current = evse.ac_power_to_current_A(22000.0)
        expected = 22000.0 / (math.sqrt(3) * 400.0)  # ~31.75 A
        assert abs(current - expected) < 0.01

    def test_ac_power_zero_returns_zero_current(self):
        """Zero power should return zero current."""
        evse = EVSE(evse_id=1, power_type="AC")
        assert evse.ac_power_to_current_A(0.0) == 0.0

    def test_round_trip_power_current_conversion(self):
        """Converting power to current and back should give same value."""
        evse = EVSE(evse_id=1, power_type="AC")
        original_power = 15000.0  # 15 kW
        current = evse.ac_power_to_current_A(original_power)
        recovered_power = evse.ac_current_to_power_W(current)
        assert abs(recovered_power - original_power) < 0.01


class TestAcChargingConstants:
    """Tests for AC charging constants."""

    def test_grid_voltage_is_400v(self):
        """AC grid voltage should be 400V (European 3-phase)."""
        assert AC_GRID_VOLTAGE_V == 400.0

    def test_sqrt3_is_correct(self):
        """SQRT3 constant should be correct."""
        assert abs(SQRT3 - math.sqrt(3)) < 0.0001

    def test_22kw_charger_draws_correct_current(self):
        """A 22 kW charger should draw approximately 32A per phase."""
        evse = EVSE(evse_id=1, power_type="AC")
        current = evse.ac_power_to_current_A(22000.0)
        # 22000 / (sqrt(3) * 400) ≈ 31.75 A
        assert 31.0 < current < 33.0

    def test_11kw_charger_draws_correct_current(self):
        """An 11 kW charger should draw approximately 16A per phase."""
        evse = EVSE(evse_id=1, power_type="AC")
        current = evse.ac_power_to_current_A(11000.0)
        # 11000 / (sqrt(3) * 400) ≈ 15.88 A
        assert 15.0 < current < 17.0
