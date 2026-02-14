"""Unit tests for ocpp_client helpers and build_connection_url."""
import json

import pytest

from simulator_core.ocpp_client import (
    _connection_is_open,
    _dict_to_meter_values_payload,
    _measurand_from_str,
    _parse_ocpp_message_type,
    _unit_from_str,
    build_connection_url,
)


@pytest.mark.unit
class TestParseOcppMessageType:
    def test_call_returns_action_name(self):
        raw = json.dumps([2, "unique-id", "BootNotification", {}])
        assert _parse_ocpp_message_type(raw) == "BootNotification"

    def test_call_result(self):
        raw = json.dumps([3, "unique-id", {}])
        assert _parse_ocpp_message_type(raw) == "CallResult"

    def test_call_error(self):
        raw = json.dumps([4, "unique-id", "ErrorCode", "Description", {}])
        assert _parse_ocpp_message_type(raw) == "CallError"

    def test_call_too_short_returns_unknown(self):
        raw = json.dumps([2, "unique-id"])
        assert _parse_ocpp_message_type(raw) == "Unknown"

    def test_unknown_type_id(self):
        raw = json.dumps([99, "x"])
        assert _parse_ocpp_message_type(raw) == "Unknown"

    def test_not_list_returns_unknown(self):
        assert _parse_ocpp_message_type('{"a":1}') == "Unknown"

    def test_invalid_json_returns_unknown(self):
        assert _parse_ocpp_message_type("not json") == "Unknown"


@pytest.mark.unit
class TestConnectionIsOpen:
    def test_open_when_state_open(self):
        try:
            from websockets.protocol import State
            class MockConn:
                state = State.OPEN
            assert _connection_is_open(MockConn()) is True
        except ImportError:
            pytest.skip("websockets not installed")

    def test_closed_when_state_not_open(self):
        try:
            from websockets.protocol import State
            class MockConn:
                state = State.CLOSED
            assert _connection_is_open(MockConn()) is False
        except ImportError:
            class MockConnNoState:
                pass
            assert _connection_is_open(MockConnNoState()) is False

    def test_no_state_returns_false(self):
        class MockConn:
            pass
        assert _connection_is_open(MockConn()) is False


@pytest.mark.unit
class TestMeasurandFromStr:
    def test_energy_active_import_register(self):
        from ocpp.v16.enums import Measurand
        assert _measurand_from_str("Energy.Active.Import.Register") == Measurand.energy_active_import_register

    def test_power_active_import(self):
        from ocpp.v16.enums import Measurand
        assert _measurand_from_str("Power.Active.Import") == Measurand.power_active_import

    def test_unknown_returns_energy_register(self):
        from ocpp.v16.enums import Measurand
        assert _measurand_from_str("Unknown.Measurand") == Measurand.energy_active_import_register


@pytest.mark.unit
class TestUnitFromStr:
    def test_wh(self):
        from ocpp.v16.enums import UnitOfMeasure
        assert _unit_from_str("Wh") == UnitOfMeasure.wh

    def test_w(self):
        from ocpp.v16.enums import UnitOfMeasure
        assert _unit_from_str("W") == UnitOfMeasure.w

    def test_unknown_returns_wh(self):
        from ocpp.v16.enums import UnitOfMeasure
        assert _unit_from_str("UnknownUnit") == UnitOfMeasure.wh


@pytest.mark.unit
class TestDictToMeterValuesPayload:
    def test_converts_payload(self):
        d = {
            "connectorId": 1,
            "transactionId": 2,
            "meterValue": [
                {
                    "timestamp": "2025-01-01T12:00:00.000Z",
                    "sampledValue": [
                        {"value": "1000", "measurand": "Energy.Active.Import.Register", "unit": "Wh"},
                        {"value": "11000", "measurand": "Power.Active.Import", "unit": "W"},
                    ],
                }
            ],
        }
        payload = _dict_to_meter_values_payload(d)
        assert payload.connector_id == 1
        assert payload.transaction_id == 2
        assert len(payload.meter_value) == 1
        assert len(payload.meter_value[0].sampled_value) == 2

    def test_with_location(self):
        d = {
            "connectorId": 1,
            "meterValue": [
                {
                    "timestamp": "2025-01-01T12:00:00.000Z",
                    "sampledValue": [
                        {"value": "50", "measurand": "SoC", "unit": "Percent", "location": "EV"},
                    ],
                }
            ],
        }
        payload = _dict_to_meter_values_payload(d)
        assert payload.meter_value[0].sampled_value[0].location == "EV"


@pytest.mark.unit
class TestBuildConnectionUrl:
    def test_adds_charge_point_id(self):
        assert build_connection_url("wss://csms.example.com/ocpp", "CP-001") == "wss://csms.example.com/ocpp/CP-001"

    def test_strips_trailing_slash(self):
        assert build_connection_url("wss://csms.example.com/", "CP-001") == "wss://csms.example.com/CP-001"
