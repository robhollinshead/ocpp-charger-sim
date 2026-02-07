# PRD: OCPP 1.6 MeterValues Simulation & Smart Charging Feedback Loop

## Overview

This PRD defines how to implement realistic, recurring `MeterValues` emission using an OCPP 1.6 simulator (based on `mobilityhouse/ocpp`) and how these values drive and validate the Smart Charging control loop in the CSMS.

The goal is to replace synthetic session injection with a protocol-accurate, time-based simulation of charger behaviour, producing realistic power and energy curves that exercise allocation, rebalancing, and fault handling.

---

## Objectives

1. Simulated chargers must send recurring `MeterValues` during active transactions.
2. Values must be realistic and physically consistent:

   * Energy is monotonic
   * Power reflects CSMS limits
   * Current derives from power and voltage
3. Each EVSE manages its own metering loop.
4. Smart Charging commands (`SetChargingProfile`) dynamically affect emitted values.
5. MeterValues stop immediately when:

   * Transaction ends
   * EVSE becomes Faulted or Unavailable
6. Behaviour must mirror real-world OCPP 1.6 chargers.

---

## Scope

### In Scope

* Python-based OCPP 1.6 simulator using `mobilityhouse/ocpp`
* Recurring MeterValues loop per EVSE
* Integration with CSMS smart charging
* AC and DC-capable behaviour model
* Scriptable timing and scenarios

### Out of Scope

* OCPP 2.0.1
* UI-based simulator control
* ISO 15118 vehicle negotiation
* Hardware-specific quirks

---

## Functional Requirements

### FR-1: Metering Loop

* For each active transaction, start one asyncio task per EVSE.
* Loop interval is configurable (default: 10s).
* Loop runs only while EVSE state == Charging.

### FR-2: Internal Meter State

Each EVSE maintains:

```python
energy_Wh: float
power_W: float
voltage_V: float
current_A: float
max_power_W: float
```

### FR-3: Value Generation Rules

| Property | Rule                            |
| -------- | ------------------------------- |
| Energy   | Increases by power * dt         |
| Power    | = min(offered_limit, max_power) |
| Current  | power / voltage                 |
| Voltage  | Fixed (e.g. 230V AC, 400V DC)   |

Energy must never decrease.

### FR-4: MeterValues Payload

Each emission must include:

* `Energy.Active.Import.Register` (Wh)
* `Power.Active.Import` (W)
* `Current.Import` (A)

Example structure:

```json
{
  "connectorId": 1,
  "transactionId": 42,
  "meterValue": [
    {
      "timestamp": "2026-01-01T12:00:00Z",
      "sampledValue": [
        {"value": "1234", "measurand": "Energy.Active.Import.Register", "unit": "Wh"},
        {"value": "7200", "measurand": "Power.Active.Import", "unit": "W"},
        {"value": "31.3", "measurand": "Current.Import", "unit": "A"}
      ]
    }
  ]
}
```

### FR-5: Smart Charging Feedback

* Simulator must handle `SetChargingProfile`.
* Extract active power limit.
* Update EVSE `power_W` accordingly.
* Next MeterValues reflects new power and energy slope.

### FR-6: Lifecycle Management

| Event              | Action               |
| ------------------ | -------------------- |
| StartTransaction   | Start metering task  |
| StopTransaction    | Cancel metering task |
| Status=Faulted     | Cancel metering task |
| Status=Unavailable | Cancel metering task |

No MeterValues may be sent after cancellation.

---

## Non-Functional Requirements

* Simulator must scale to 50+ chargers
* No shared global timers
* Deterministic behaviour under identical scenarios
* Async-safe cancellation
* CI-friendly (headless execution)

---

## Implementation Guidance

### Metering Loop Pattern

```python
async def _metering_loop(evse_id, transaction_id):
    while charging:
        update_internal_state()
        await send_meter_values()
        await asyncio.sleep(interval)
```

One loop per EVSE. No global schedulers.

### Charging Profile Application

```python
def apply_charging_profile(evse_id, limit_W):
    meter.power_W = min(limit_W, meter.max_power_W)
```

---

## Acceptance Criteria

1. During an active session, MeterValues arrive at CSMS at configured interval.
2. Energy increases smoothly over time.
3. Reducing power via `SetChargingProfile` reduces slope of energy curve.
4. MeterValues stop within one interval of StopTransaction.
5. Multi-charger scenarios run without task leaks.
6. CSMS smart charging reacts only to OCPP inputs.

---

## Test Scenarios

1. Single AC charger, 7kW flat curve
2. 20 chargers starting within 2 minutes
3. Mid-session power reduction
4. Fault during charging
5. Rapid start/stop churn

---

## Success Metrics

* No proprietary injection path used
* Power allocation correctness validated numerically
* Smart charging observable end-to-end via OCPP
* Simulator produces production-like traffic

---

## Future Enhancements

* DC fast-charge taper curves
* Phase-level current reporting
* SoC-based profiles
* OCPP 2.0.1 migration
