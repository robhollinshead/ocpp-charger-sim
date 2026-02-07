# OCPP 1.6 Simulator Integration Plan

## Purpose

This document provides a **detailed, step-by-step implementation plan** for integrating an **OCPP 1.6 JSON simulator** into the existing Smart Charging CSMS backend. It is intended for use by an AI coding agent or developer to implement the solution incrementally.

Goals:

* Replace proprietary session injection with **realistic OCPP message flows**
* Enable **scriptable, multi‑charger simulation** in development and CI
* Ensure **zero architectural divergence** between simulator-based dev and real chargers in production
* Drive **existing smart charging logic** exclusively from OCPP events

---

## Non‑Goals

* Supporting OCPP 2.0.1 (out of scope for this phase)
* UI for simulator control (CLI & scripts only)
* Hardware‑specific charger quirks

---

## Architectural Principles

1. **CSMS must not know whether a charger is simulated or real**
2. **All charging sessions originate from OCPP messages**
3. **Smart charging logic remains unchanged** — only its inputs/outputs change
4. **Simulator runs as a separate service**

---

## High‑Level Architecture

```
+----------------------+        WebSocket (OCPP 1.6)        +----------------------+
| OCPP Simulator(s)   | <-------------------------------> | CSMS Backend         |
| (Python, scripted)  |                                   | (existing app)       |
+----------------------+                                   +----------------------+
```

In production, the simulator is **not deployed** and real chargers connect instead.

---

## Technology Choices

### OCPP Library

* **mobilityhouse/ocpp** (Python)

  * Supports OCPP 1.6 JSON
  * Async, WebSocket‑based
  * Actively maintained

### Transport

* WebSocket (per OCPP 1.6 spec)

### Simulator Control

* Python scripts
* CLI entrypoints (argparse / click)

---

## Phase 1 — CSMS: Introduce OCPP Gateway Layer

### Objective

Add a dedicated OCPP ingress/egress layer that translates protocol messages into domain events.

### Tasks

#### 1.1 Create OCPP Server Module

Structure:

```
csms/
  ocpp/
    server.py
    connection_manager.py
    handlers/
      boot_notification.py
      heartbeat.py
      status_notification.py
      start_transaction.py
      stop_transaction.py
      meter_values.py
```

Responsibilities:

* Accept WebSocket connections
* Maintain charge point connections
* Route messages to handlers

---

#### 1.2 Implement Core Message Handlers

Each handler must:

* Validate message
* Map OCPP payload → domain command/event
* Be idempotent

Minimum required messages:

| OCPP Message       | Purpose                |
| ------------------ | ---------------------- |
| BootNotification   | Register charger       |
| Heartbeat          | Keepalive              |
| StatusNotification | EVSE state changes     |
| StartTransaction   | Session start          |
| MeterValues        | Power / energy updates |
| StopTransaction    | Session end            |

---

#### 1.3 Disable Proprietary Session Injection (Dev Only)

* Keep code path behind feature flag
* Simulator‑driven OCPP becomes default input in dev

---

## Phase 2 — Map OCPP to Existing Domain Model

### Objective

Ensure **all existing session, EVSE, and load logic** is driven by OCPP events.

### Required Mappings

| OCPP Event                     | Domain Effect                   |
| ------------------------------ | ------------------------------- |
| BootNotification               | Create / update charger & EVSEs |
| StatusNotification (Preparing) | Plug‑in detected                |
| StartTransaction               | Create charging session         |
| MeterValues                    | Update session metrics          |
| StatusNotification (Faulted)   | EVSE unavailable                |
| StopTransaction                | End session                     |

### Rules

* CSMS is source of truth
* Simulator never writes DB directly
* All state transitions must be reproducible from OCPP history

---

## Phase 3 — Smart Charging via OCPP

### Objective

Close the control loop using **SetChargingProfile**.

### Tasks

#### 3.1 Charging Profile Generator

* Convert existing power allocation output into OCPP `ChargingProfile`
* Profile granularity: 1‑minute periods

#### 3.2 OCPP Command Sender

* Maintain per‑EVSE control channel
* Send `SetChargingProfile` on:

  * Session start
  * Rebalancing tick
  * Session end

---

## Phase 4 — OCPP Simulator Service

### Objective

Provide a realistic, scriptable charge point simulator.

### Simulator Structure

```
ocpp_sim/
  charge_point.py
  evse.py
  simulator_runner.py
  scenarios/
    basic_charge.py
    morning_rush.py
    fault_injection.py
  cli.py
  config.yaml
```

---

### 4.1 Simulated Charge Point

Capabilities:

* Connect to CSMS via WebSocket
* Send BootNotification
* Support 1–N EVSEs
* Handle SetChargingProfile
* Maintain local state machine

---

### 4.2 EVSE State Machine

States:

* Available
* Preparing
* Charging
* Faulted
* Unavailable

Transitions triggered by:

* Scenario scripts
* CSMS commands

---

### 4.3 Scenario Engine

Scenarios are Python scripts that:

* Spawn N chargers
* Control timing of events
* Inject faults
* Run deterministically

Example scenarios:

* **Single normal charge**
* **Depot morning rush (20+ chargers)**
* **Mid‑session fault**
* **Power constraint saturation**

---

### 4.4 CLI Interface

Commands:

```
start-sim --chargers 10 --evses 2
run-scenario morning_rush
inject-fault CP_01 EVSE_2
stop-sim
```

CLI must:

* Be scriptable
* Return non‑zero exit codes on failure

---

## Phase 5 — Dev, CI, and Production Strategy

### Environment Mapping

| Environment | Charger Source             |
| ----------- | -------------------------- |
| Local Dev   | Simulator                  |
| CI          | Headless simulator         |
| Staging     | Simulator + pilot chargers |
| Production  | Real chargers              |

### Key Rule

**CSMS binary is identical in all environments**.

---

## Phase 6 — Testing Strategy

### Automated Tests

* OCPP handler unit tests
* Scenario‑based integration tests
* Power allocation regression tests

### Metrics to Validate

* Session lifecycle correctness
* Power limit enforcement
* Recovery from faults
* Deterministic replay

---

## Deliverables Checklist

* [ ] OCPP WebSocket server in CSMS
* [ ] OCPP → domain event mapping
* [ ] SetChargingProfile integration
* [ ] Python OCPP simulator service
* [ ] CLI + scripted scenarios
* [ ] Documentation & example runs

---

## Success Criteria

* CSMS operates correctly with **no proprietary injection**
* Simulator can scale to 50+ chargers
* Same codebase works unchanged with real hardware
* Smart charging behavior observable via OCPP only

---

## Future Extensions (Not in Scope)

* OCPP 2.0.1 support
* REST control plane for simulator
* Charger‑specific behavior profiles
* Hardware‑in‑the‑loop testing
