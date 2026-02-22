export type ChargerStatus = 'Available' | 'Charging' | 'Preparing' | 'Offline' | 'Faulted';

export interface Location {
  id: string;
  name: string;
  address: string;
  chargerCount: number;
}

/** Payload for creating a location (API request). */
export interface LocationCreate {
  name: string;
  address: string;
}

/** Raw location from API (snake_case). */
export interface LocationResponse {
  id: string;
  name: string;
  address: string;
  charger_count: number;
}

export interface Charger {
  id: string;
  charge_point_id: string;
  connection_url: string;
  charger_name: string;
  ocpp_version: string;
  location_id: string;
  evse_count: number;
  connected: boolean;
  power_type?: 'AC' | 'DC';
  ocpp_status?: string | null;
}

/** Payload for creating a charger (API request). */
export interface ChargerCreate {
  connection_url: string;
  charge_point_id: string;
  charger_name: string;
  ocpp_version?: string;
  evse_count?: number;
  charge_point_vendor?: string;
  charge_point_model?: string;
  firmware_version?: string;
}

/** Supported OCPP versions. */
export const OCPP_VERSIONS = ['1.6', '2.0.1'] as const;

/** Payload for updating a charger (API request). */
export interface ChargerUpdate {
  connection_url?: string;
  charger_name?: string;
  ocpp_version?: string;
  security_profile?: 'none' | 'basic';
  basic_auth_password?: string;
}

/** Raw charger from API (snake_case). */
export interface ChargerResponse {
  id: string;
  charge_point_id: string;
  connection_url: string;
  charger_name: string;
  ocpp_version: string;
  location_id: string;
  evse_count: number;
  connected: boolean;
  power_type?: 'AC' | 'DC';
  ocpp_status?: string | null;
}

/** Evse status from API (snake_case). */
export interface EvseStatusResponse {
  evse_id: number;
  state: string;
  transaction_id: number | null;
  id_tag?: string | null;
  session_start_time?: string | null;
  meter: { energy_Wh: number; power_W: number; voltage_V: number; current_A: number };
}

/** Raw charger detail from API (includes evses, config, identity). */
export interface ChargerDetailResponse extends ChargerResponse {
  charge_point_vendor?: string;
  charge_point_model?: string;
  firmware_version?: string;
  evses: EvseStatusResponse[];
  config: Record<string, string | number | boolean>;
  security_profile?: 'none' | 'basic';
  basic_auth_password_set?: boolean;
  power_type?: 'AC' | 'DC';
}

/** Payload for updating charger OCPP config (API request). */
export interface ChargerConfigUpdate {
  HeartbeatInterval?: number;
  ConnectionTimeOut?: number;
  MeterValuesSampleInterval?: number;
  ClockAlignedDataInterval?: number;
  AuthorizeRemoteTxRequests?: boolean;
  LocalAuthListEnabled?: boolean;
  OCPPAuthorizationEnabled?: boolean;
}


export interface Connector {
  id: number;
  status: ChargerStatus;
  type: string;
  maxPower: number;
}

export interface OCPPLog {
  id: string;
  timestamp: string;
  direction: 'incoming' | 'outgoing';
  messageType: string;
  payload: string;
  status: 'success' | 'error' | 'pending';
}

export interface Transaction {
  id: string;
  connectorId: number;
  startTime: string;
  endTime?: string;
  meterStart: number;
  meterStop?: number;
  idTag: string;
  status: 'active' | 'completed' | 'stopped';
}

export interface ChargingScenario {
  id: string;
  name: string;
  description: string;
  vehicleCount: number;
  duration: string;
  pattern: 'sequential' | 'random' | 'burst';
}

export interface ChargerConfig {
  key: string;
  value: string;
  readonly: boolean;
  type: 'string' | 'number' | 'boolean';
}

/** Vehicle (normalized for UI). */
export interface Vehicle {
  id: string;
  name: string;
  idTags: string[];
  battery_capacity_kWh: number;
  location_id: string;
}

/** Payload for creating a vehicle (API request). */
export interface VehicleCreate {
  name: string;
  idTags: string[];
  battery_capacity_kWh: number;
}

/** Raw vehicle from API. */
export interface VehicleResponse {
  id: string;
  name: string;
  idTags: string[];
  battery_capacity_kWh: number;
  location_id: string;
}

/** Result of an import (chargers or vehicles). */
export interface ImportResult<T> {
  success: T[];
  failed: { row: unknown; error: string }[];
}
