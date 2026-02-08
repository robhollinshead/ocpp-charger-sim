import { OCPPLog, Transaction, ChargingScenario } from '@/types/ocpp';

export const ocppLogs: OCPPLog[] = [
  { id: '1', timestamp: '2024-01-15T10:30:00Z', direction: 'incoming', messageType: 'Heartbeat', payload: '{}', status: 'success' },
  { id: '2', timestamp: '2024-01-15T10:29:55Z', direction: 'outgoing', messageType: 'HeartbeatResponse', payload: '{"currentTime": "2024-01-15T10:29:55Z"}', status: 'success' },
  { id: '3', timestamp: '2024-01-15T10:29:30Z', direction: 'incoming', messageType: 'StatusNotification', payload: '{"connectorId": 1, "status": "Charging", "errorCode": "NoError"}', status: 'success' },
  { id: '4', timestamp: '2024-01-15T10:29:00Z', direction: 'incoming', messageType: 'StartTransaction', payload: '{"connectorId": 1, "idTag": "ABC123", "meterStart": 0}', status: 'success' },
  { id: '5', timestamp: '2024-01-15T10:28:55Z', direction: 'outgoing', messageType: 'StartTransactionResponse', payload: '{"transactionId": 12345, "idTagInfo": {"status": "Accepted"}}', status: 'success' },
  { id: '6', timestamp: '2024-01-15T10:28:30Z', direction: 'incoming', messageType: 'Authorize', payload: '{"idTag": "ABC123"}', status: 'success' },
  { id: '7', timestamp: '2024-01-15T10:28:00Z', direction: 'incoming', messageType: 'BootNotification', payload: '{"chargePointVendor": "FastCharge", "chargePointModel": "Pro 150"}', status: 'error' },
];

export const transactions: Transaction[] = [
  { id: 'tx-001', connectorId: 1, startTime: '2024-01-15T10:29:00Z', meterStart: 0, idTag: 'ABC123', status: 'active' },
  { id: 'tx-002', connectorId: 1, startTime: '2024-01-15T08:00:00Z', endTime: '2024-01-15T09:30:00Z', meterStart: 0, meterStop: 45000, idTag: 'DEF456', status: 'completed' },
  { id: 'tx-003', connectorId: 2, startTime: '2024-01-15T07:00:00Z', endTime: '2024-01-15T07:45:00Z', meterStart: 0, meterStop: 22500, idTag: 'GHI789', status: 'completed' },
];

export const chargingScenarios: ChargingScenario[] = [
  { id: 'scen-1', name: 'Overnight Fleet Charging', description: 'Simulates a fleet of delivery vehicles charging overnight', vehicleCount: 20, duration: '8 hours', pattern: 'sequential' },
  { id: 'scen-2', name: 'Peak Hour Rush', description: 'Simulates high demand during peak commute hours', vehicleCount: 50, duration: '2 hours', pattern: 'burst' },
  { id: 'scen-3', name: 'Random Daily Usage', description: 'Simulates typical daily charging patterns', vehicleCount: 30, duration: '12 hours', pattern: 'random' },
  { id: 'scen-4', name: 'Stress Test', description: 'Maximum capacity test for all chargers', vehicleCount: 100, duration: '1 hour', pattern: 'burst' },
];
