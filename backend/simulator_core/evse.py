"""EVSE state machine and internal meter state (OCPP 1.6)."""
import math
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from simulator_core.dc_voltage import DEFAULT_CELLS, get_pack_voltage_V

# AC charger constants (3-phase, 400V line-to-line)
AC_GRID_VOLTAGE_V = 400.0
SQRT3 = math.sqrt(3)


class EvseState(str, Enum):
    """EVSE connector states per OCPP 1.6 StatusNotification."""
    Available = "Available"
    Preparing = "Preparing"
    Charging = "Charging"
    SuspendedEV = "SuspendedEV"
    SuspendedEVSE = "SuspendedEVSE"
    Finishing = "Finishing"
    Faulted = "Faulted"
    Unavailable = "Unavailable"


# Valid state transitions: from_state -> set of allowed to_states
_VALID_TRANSITIONS: dict[EvseState, set[EvseState]] = {
    EvseState.Available: {EvseState.Preparing, EvseState.Unavailable},
    EvseState.Preparing: {EvseState.Charging, EvseState.Available, EvseState.Faulted, EvseState.Unavailable},
    EvseState.Charging: {
        EvseState.Finishing,
        EvseState.SuspendedEV,
        EvseState.SuspendedEVSE,
        EvseState.Faulted,
        EvseState.Unavailable,
    },
    EvseState.SuspendedEV: {EvseState.Charging, EvseState.Finishing, EvseState.Faulted, EvseState.Unavailable},
    EvseState.SuspendedEVSE: {EvseState.Charging, EvseState.Finishing, EvseState.Faulted, EvseState.Unavailable},
    EvseState.Finishing: {EvseState.Available, EvseState.Faulted, EvseState.Unavailable},
    EvseState.Faulted: {EvseState.Available, EvseState.Unavailable},
    EvseState.Unavailable: {EvseState.Available},
}


class EVSE:
    """
    Single EVSE (connector): state machine and internal meter state.
    Meter fields follow ocpp-meter-values.md FR-2.
    """

    __slots__ = (
        "evse_id",
        "state",
        "energy_Wh",
        "power_W",
        "current_A",
        "max_power_W",
        "offered_limit_W",
        "transaction_id",
        "_initial_energy_Wh",
        "id_tag",
        "session_start_time",
        "start_soc_pct",
        "battery_capacity_Wh",
        "soc_pct",
        "power_type",
    )

    def __init__(
        self,
        evse_id: int,
        max_power_W: float = 22000.0,  # not currently used as a hard limit; SetChargingProfile dictates power
        power_type: str = "DC",
    ) -> None:
        self.evse_id = evse_id
        self.state = EvseState.Available
        self.energy_Wh = 0.0
        self.power_W = 0.0
        self.current_A = 0.0
        self.max_power_W = max_power_W
        self.offered_limit_W = 0.0  # 0 until SetChargingProfile from CSMS
        self.transaction_id: Optional[int] = None
        self._initial_energy_Wh = 0.0  # at StartTransaction
        self.id_tag: Optional[str] = None
        self.session_start_time: Optional[str] = None
        self.start_soc_pct = 20.0
        self.battery_capacity_Wh = 100_000.0
        self.soc_pct = 20.0
        self.power_type = power_type  # "AC" or "DC", propagated from parent Charger

    def transition_to(self, new_state: EvseState) -> bool:
        """Validate and perform state transition. Returns True if applied."""
        allowed = _VALID_TRANSITIONS.get(self.state)
        if allowed is None or new_state not in allowed:
            return False
        self.state = new_state
        return True

    def can_transition_to(self, new_state: EvseState) -> bool:
        """Check if transition is allowed without applying."""
        allowed = _VALID_TRANSITIONS.get(self.state)
        return allowed is not None and new_state in allowed

    def set_offered_limit_W(self, limit_W: float) -> None:
        """Apply power limit from SetChargingProfile (FR-5). CSMS limit is stored as-is for simulation."""
        self.offered_limit_W = max(0.0, limit_W)

    def get_effective_power_W(self) -> float:
        """Power for meter: CSMS limit from SetChargingProfile (no cap by max_power for simulation).
        Returns 0 when suspended (SuspendedEV/SuspendedEVSE) so no power is simulated regardless of profile.
        """
        if self.state in (EvseState.SuspendedEV, EvseState.SuspendedEVSE):
            return 0.0
        return self.offered_limit_W

    def get_voltage_V(self) -> float:
        """Compute voltage: AC returns fixed 400V grid voltage, DC uses sigmoid OCV model."""
        if self.power_type == "AC":
            return AC_GRID_VOLTAGE_V
        return get_pack_voltage_V(self.soc_pct, DEFAULT_CELLS)

    def get_meter_snapshot(self) -> dict[str, float]:
        """Current meter values for MeterValues payload (FR-4)."""
        return {
            "energy_Wh": self.energy_Wh,
            "power_W": self.power_W,
            "voltage_V": self.get_voltage_V(),
            "current_A": self.current_A,
        }

    def ac_current_to_power_W(self, current_A: float) -> float:
        """Convert current (A) to power (W) for 3-phase AC: P = sqrt(3) * V * I."""
        return SQRT3 * AC_GRID_VOLTAGE_V * current_A

    def ac_power_to_current_A(self, power_W: float) -> float:
        """Convert power (W) to current (A) for 3-phase AC: I = P / (sqrt(3) * V)."""
        return power_W / (SQRT3 * AC_GRID_VOLTAGE_V) if power_W > 0 else 0.0

    def start_transaction(
        self,
        transaction_id: int,
        id_tag: str = "",
        *,
        start_soc_pct: float = 20.0,
        battery_capacity_wh: float = 100.0,
    ) -> None:
        """Record transaction start; set initial energy, id_tag, session_start_time, SoC params."""
        self.transaction_id = transaction_id
        self._initial_energy_Wh = self.energy_Wh
        self.id_tag = id_tag or None
        self.session_start_time = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self.start_soc_pct = start_soc_pct
        self.battery_capacity_Wh = battery_capacity_wh * 1000.0
        self.soc_pct = start_soc_pct

    def end_transaction(self) -> None:
        """Clear transaction id, id_tag and session_start_time after StopTransaction."""
        self.transaction_id = None
        self.id_tag = None
        self.session_start_time = None

    def reset_meter_for_session(self) -> None:
        """Optional: zero energy at session start. Not required by spec (monotonic)."""
        pass  # We keep energy monotonic; session uses _initial_energy_Wh if needed for stop meter
