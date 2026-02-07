# OCPP Gateway Testing Guide

This document explains how to manually verify and test the OCPP gateway functionality.

## Manual Verification

### Prerequisites

1. **Start the backend server:**
   ```bash
   cd backend
   python run.py
   ```

2. **Ensure you have a charger in the database** with an `ocpp_charge_point_id` set:
   - You can create one via the API or use the depot builder UI
   - The charge point ID should match what you use in the WebSocket URL (e.g., `CP_001`)
   
   **Quick setup via API:**
   ```bash
   # First, create a constraint hierarchy (if not already exists)
   curl -X POST "http://localhost:8000/api/v1/constraints" \
     -H "Content-Type: application/json" \
     -d '{
       "name": "Test Depot",
       "max_power_kw": 1000.0,
       "priority": 1,
       "type": "constraint"
     }'
   
   # Create a charge group
   curl -X POST "http://localhost:8000/api/v1/constraints" \
     -H "Content-Type: application/json" \
     -d '{
       "name": "Test Charge Group",
       "max_power_kw": 500.0,
       "priority": 2,
       "type": "charge_group",
       "parent_id": "<constraint_id_from_above>"
     }'
   
   # Create a charger with OCPP charge point ID
   curl -X POST "http://localhost:8000/api/v1/chargers" \
     -H "Content-Type: application/json" \
     -d '{
       "name": "Test Charger",
       "max_power_kw": 100.0,
       "parent_charge_group": "<charge_group_id_from_above>",
       "is_active": "Active",
       "status": "Available",
       "ocpp_charge_point_id": "CP_001",
       "evses": [
         {"id": 1, "max_power_kw": 50.0, "status": "Available"}
       ]
     }'
   ```
   
   **Or check existing chargers:**
   ```bash
   curl "http://localhost:8000/api/v1/chargers" | jq '.[] | {id, name, ocpp_charge_point_id}'
   ```

3. **Install websockets library** (if not already installed):
   ```bash
   pip install websockets
   ```

### Using the Manual Test Script

The `scripts/test_ocpp_manual.py` script allows you to manually test OCPP messages:

#### Basic Usage

```bash
# Test BootNotification
python scripts/test_ocpp_manual.py \
  --charge-point-id CP_001 \
  --action BootNotification

# Test Heartbeat
python scripts/test_ocpp_manual.py \
  --charge-point-id CP_001 \
  --action Heartbeat

# Test StatusNotification (EVSE status change)
python scripts/test_ocpp_manual.py \
  --charge-point-id CP_001 \
  --action StatusNotification \
  --connector-id 1 \
  --status Charging

# Test StartTransaction
python scripts/test_ocpp_manual.py \
  --charge-point-id CP_001 \
  --action StartTransaction \
  --connector-id 1 \
  --id-tag TEST_TAG

# Test StopTransaction (requires transaction ID from StartTransaction)
python scripts/test_ocpp_manual.py \
  --charge-point-id CP_001 \
  --action StopTransaction \
  --transaction-id 123456789 \
  --id-tag TEST_TAG

# Test MeterValues
python scripts/test_ocpp_manual.py \
  --charge-point-id CP_001 \
  --action MeterValues \
  --connector-id 1 \
  --transaction-id 123456789
```

#### Options

- `--charge-point-id`: OCPP charge point ID (required)
- `--action`: OCPP action to send (required)
- `--host`: Server host (default: localhost)
- `--port`: Server port (default: 8000)
- `--connector-id`: EVSE/connector ID (required for StatusNotification, StartTransaction, MeterValues)
- `--status`: Status value (for StatusNotification)
- `--transaction-id`: Transaction ID (required for StopTransaction)
- `--id-tag`: RFID tag ID (default: TEST_TAG)

#### Example Workflow

1. **Connect and register charger:**
   ```bash
   python scripts/test_ocpp_manual.py --charge-point-id CP_001 --action BootNotification
   ```

2. **Change EVSE status:**
   ```bash
   python scripts/test_ocpp_manual.py --charge-point-id CP_001 --action StatusNotification --connector-id 1 --status Preparing
   ```

3. **Start a charging session:**
   ```bash
   python scripts/test_ocpp_manual.py --charge-point-id CP_001 --action StartTransaction --connector-id 1
   ```
   Note the `transactionId` from the response.

4. **Send meter values:**
   ```bash
   python scripts/test_ocpp_manual.py --charge-point-id CP_001 --action MeterValues --connector-id 1 --transaction-id <transaction_id>
   ```

5. **Stop the session:**
   ```bash
   python scripts/test_ocpp_manual.py --charge-point-id CP_001 --action StopTransaction --transaction-id <transaction_id>
   ```

### Manual Verification Checklist

- [ ] WebSocket connection is accepted
- [ ] BootNotification returns "Accepted" status
- [ ] Heartbeat returns current time
- [ ] StatusNotification updates EVSE status in database
- [ ] StartTransaction creates a charging session
- [ ] MeterValues are received and logged
- [ ] StopTransaction ends the session
- [ ] Invalid messages return appropriate errors
- [ ] Connection is properly cleaned up on disconnect

### Verifying Database State

After sending OCPP messages, you can verify the database state:

```bash
# Check charger status
curl http://localhost:8000/api/v1/chargers

# Check active sessions
curl http://localhost:8000/api/v1/sessions/live

# Check connection status (via logs or connection manager)
```

## Automated Unit Tests

### Running Unit Tests

```bash
# Run all OCPP tests
pytest backend/tests/unit/test_ocpp_handlers.py -v
pytest backend/tests/unit/test_ocpp_connection_manager.py -v

# Run integration tests
pytest backend/tests/integration/test_ocpp_websocket.py -v

# Run all OCPP-related tests
pytest backend/tests/ -k ocpp -v
```

### Test Coverage

#### Unit Tests (`test_ocpp_handlers.py`)

- ✅ BootNotification handler validation
- ✅ Heartbeat handler
- ✅ StatusNotification handler (all status types)
- ✅ StartTransaction handler (session creation)
- ✅ StopTransaction handler (session ending)
- ✅ MeterValues handler
- ✅ Error handling for invalid payloads
- ✅ Missing field validation

#### Connection Manager Tests (`test_ocpp_connection_manager.py`)

- ✅ Connection registration
- ✅ Connection lookup
- ✅ Connection unregistration
- ✅ Multiple connections isolation
- ✅ Connection state tracking

#### Integration Tests (`test_ocpp_websocket.py`)

- ✅ WebSocket connection establishment
- ✅ Message routing
- ✅ Response formatting
- ✅ Invalid JSON handling
- ✅ Invalid message format handling
- ✅ Unknown action handling

### Test Structure

Tests use the existing test fixtures from `conftest.py`:
- `db_session`: Isolated database session
- `created_charger`: Pre-created charger with EVSEs
- `created_vehicle`: Pre-created vehicle

All tests are isolated and use in-memory SQLite databases.

## Debugging Tips

### Check Server Logs

The OCPP gateway logs all messages and errors. Check the server output for:
- Connection acceptance/rejection
- Message parsing errors
- Handler execution
- Database update results

### Common Issues

1. **"Charger not found" error (1008 policy violation):**
   - **Most common cause**: The charger doesn't exist or doesn't have `ocpp_charge_point_id` set
   - **Solution**: 
     ```bash
     # Check if charger exists
     curl "http://localhost:8000/api/v1/chargers" | jq '.[] | select(.ocpp_charge_point_id == "CP_001")'
     
     # If charger exists but no ocpp_charge_point_id, update it:
     curl -X PUT "http://localhost:8000/api/v1/chargers/<charger_id>" \
       -H "Content-Type: application/json" \
       -d '{"ocpp_charge_point_id": "CP_001"}'
     ```
   - Verify `ocpp_charge_point_id` matches the URL parameter exactly (case-sensitive)
   - Check database connection

2. **"No response received":**
   - Verify server is running
   - Check WebSocket endpoint is accessible
   - Review server logs for errors

3. **"Invalid message format":**
   - Ensure message follows OCPP 1.6 JSON format: `[MessageTypeId, UniqueId, Action, Payload]`
   - Verify JSON is valid

4. **"Session not found" (StopTransaction):**
   - Ensure StartTransaction was successful
   - Use the correct transaction ID from StartTransaction response

## Next Steps

After verifying basic functionality:

1. **Test error scenarios:**
   - Invalid charge point IDs
   - Missing required fields
   - Invalid EVSE IDs
   - Network disconnections

2. **Test concurrent connections:**
   - Multiple charge points connecting simultaneously
   - Multiple EVSEs on same charger

3. **Test full session lifecycle:**
   - Complete charging session from start to finish
   - Multiple sessions on different EVSEs
   - Session with meter value updates

4. **Integration with load balancer:**
   - Verify sessions trigger load balancing
   - Check power allocation updates
   - Test constraint hierarchy updates

