import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type {
  Charger,
  ChargerConfigUpdate,
  ChargerCreate,
  ChargerDetailResponse,
  ChargerResponse,
  ChargerUpdate,
  OCPPLog,
} from '@/types/ocpp';
import { apiFetch } from '@/lib/api';

const API_PREFIX = '/api';

function mapResponseToCharger(r: ChargerResponse | ChargerDetailResponse): Charger {
  const evseCount = 'evses' in r && Array.isArray(r.evses) ? r.evses.length : r.evse_count;
  return {
    id: r.id,
    charge_point_id: r.charge_point_id,
    connection_url: r.connection_url,
    charger_name: r.charger_name,
    ocpp_version: r.ocpp_version,
    location_id: r.location_id,
    evse_count: evseCount,
    connected: r.connected,
  };
}

export async function fetchChargersByLocation(locationId: string): Promise<Charger[]> {
  const data = await apiFetch<ChargerResponse[]>(`${API_PREFIX}/locations/${locationId}/chargers`);
  return data.map(mapResponseToCharger);
}

export async function createCharger(locationId: string, payload: ChargerCreate): Promise<Charger> {
  const data = await apiFetch<ChargerResponse>(`${API_PREFIX}/locations/${locationId}/chargers`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  return mapResponseToCharger(data);
}

export async function fetchChargerDetail(chargePointId: string): Promise<ChargerDetailResponse> {
  return apiFetch<ChargerDetailResponse>(`${API_PREFIX}/chargers/${chargePointId}`);
}

export async function deleteCharger(chargePointId: string): Promise<void> {
  await apiFetch(`${API_PREFIX}/chargers/${chargePointId}`, { method: 'DELETE' });
}

export async function updateCharger(chargePointId: string, payload: ChargerUpdate): Promise<Charger> {
  const data = await apiFetch<ChargerResponse>(`${API_PREFIX}/chargers/${chargePointId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
  return mapResponseToCharger(data);
}

export async function updateChargerConfig(
  chargePointId: string,
  payload: ChargerConfigUpdate
): Promise<ChargerDetailResponse> {
  return apiFetch<ChargerDetailResponse>(`${API_PREFIX}/chargers/${chargePointId}/config`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export async function connectCharger(chargePointId: string): Promise<{ status: string; charge_point_id: string }> {
  return apiFetch<{ status: string; charge_point_id: string }>(
    `${API_PREFIX}/chargers/${chargePointId}/connect`,
    { method: 'POST' }
  );
}

export async function disconnectCharger(chargePointId: string): Promise<void> {
  await apiFetch(`${API_PREFIX}/chargers/${chargePointId}/disconnect`, { method: 'POST' });
}

export async function fetchChargerLogs(chargePointId: string): Promise<OCPPLog[]> {
  return apiFetch<OCPPLog[]>(`${API_PREFIX}/chargers/${chargePointId}/logs`);
}

export async function clearChargerLogs(chargePointId: string): Promise<void> {
  await apiFetch(`${API_PREFIX}/chargers/${chargePointId}/logs`, { method: 'DELETE' });
}

export interface StartTransactionPayload {
  connector_id: number;
  id_tag: string;
}

export interface StartTransactionResponse {
  transaction_id: number;
}

export async function startTransaction(
  chargePointId: string,
  payload: StartTransactionPayload
): Promise<StartTransactionResponse> {
  return apiFetch<StartTransactionResponse>(
    `${API_PREFIX}/chargers/${chargePointId}/transactions/start`,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    }
  );
}

export interface StopTransactionPayload {
  connector_id: number;
}

export async function stopTransaction(
  chargePointId: string,
  payload: StopTransactionPayload
): Promise<void> {
  await apiFetch(`${API_PREFIX}/chargers/${chargePointId}/transactions/stop`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function chargersQueryKey(locationId: string) {
  return ['chargers', locationId] as const;
}

export function useChargers(locationId: string | undefined) {
  return useQuery({
    queryKey: chargersQueryKey(locationId ?? ''),
    queryFn: () => fetchChargersByLocation(locationId!),
    enabled: !!locationId,
  });
}

export function useCreateCharger(locationId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ChargerCreate) => createCharger(locationId!, payload),
    onSuccess: () => {
      if (locationId) {
        queryClient.invalidateQueries({ queryKey: chargersQueryKey(locationId) });
        queryClient.invalidateQueries({ queryKey: ['locations'] });
      }
    },
  });
}

export function useChargerDetail(
  chargePointId: string | undefined,
  options?: { refetchInterval?: number | false | ((query: { state: { data?: ChargerDetailResponse } }) => number | false) }
) {
  return useQuery({
    queryKey: ['chargers', 'detail', chargePointId],
    queryFn: () => fetchChargerDetail(chargePointId!),
    enabled: !!chargePointId,
    ...options,
  });
}

export function useDeleteCharger(locationId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (chargePointId: string) => deleteCharger(chargePointId),
    onSuccess: (_, chargePointId) => {
      if (locationId) {
        queryClient.invalidateQueries({ queryKey: chargersQueryKey(locationId) });
        queryClient.invalidateQueries({ queryKey: ['locations'] });
      }
      queryClient.invalidateQueries({ queryKey: ['chargers', 'detail', chargePointId] });
    },
  });
}

export function useUpdateCharger(locationId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ chargePointId, payload }: { chargePointId: string; payload: ChargerUpdate }) =>
      updateCharger(chargePointId, payload),
    onSuccess: (_, variables) => {
      if (locationId) {
        queryClient.invalidateQueries({ queryKey: chargersQueryKey(locationId) });
      }
      queryClient.invalidateQueries({ queryKey: ['chargers', 'detail', variables.chargePointId] });
    },
  });
}

export function useUpdateChargerConfig(chargePointId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ChargerConfigUpdate) => updateChargerConfig(chargePointId!, payload),
    onSuccess: () => {
      if (chargePointId) {
        queryClient.invalidateQueries({ queryKey: ['chargers', 'detail', chargePointId] });
      }
    },
  });
}

export function chargerLogsQueryKey(chargePointId: string) {
  return ['chargers', 'logs', chargePointId] as const;
}

export function useChargerLogs(chargePointId: string | undefined, refetchInterval?: number) {
  return useQuery({
    queryKey: chargerLogsQueryKey(chargePointId ?? ''),
    queryFn: () => fetchChargerLogs(chargePointId!),
    enabled: !!chargePointId,
    refetchInterval: refetchInterval ?? false,
  });
}

// Refetch charger data after connect so UI shows connected state (connection is established async)
const CONNECT_REFETCH_DELAYS_MS = [1000, 2500, 5000];

export function useConnectCharger(locationId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (chargePointId: string) => connectCharger(chargePointId),
    onSuccess: (_, chargePointId) => {
      const refetch = () => {
        if (locationId) {
          void queryClient.refetchQueries({ queryKey: chargersQueryKey(locationId) });
        }
        void queryClient.refetchQueries({ queryKey: ['chargers', 'detail', chargePointId] });
      };
      refetch();
      CONNECT_REFETCH_DELAYS_MS.forEach((delayMs) => setTimeout(refetch, delayMs));
    },
  });
}

export function useDisconnectCharger(locationId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (chargePointId: string) => disconnectCharger(chargePointId),
    onSuccess: (_, chargePointId) => {
      if (locationId) {
        queryClient.invalidateQueries({ queryKey: chargersQueryKey(locationId) });
      }
      queryClient.invalidateQueries({ queryKey: ['chargers', 'detail', chargePointId] });
    },
  });
}

export function useClearChargerLogs(chargePointId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => clearChargerLogs(chargePointId!),
    onSuccess: () => {
      if (chargePointId) {
        queryClient.invalidateQueries({ queryKey: chargerLogsQueryKey(chargePointId) });
      }
    },
  });
}

export function useStartTransaction(chargePointId: string | undefined, locationId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: StartTransactionPayload) => startTransaction(chargePointId!, payload),
    onSuccess: () => {
      if (chargePointId) {
        queryClient.invalidateQueries({ queryKey: ['chargers', 'detail', chargePointId] });
      }
      if (locationId) {
        queryClient.invalidateQueries({ queryKey: chargersQueryKey(locationId) });
      }
    },
  });
}

export function useStopTransaction(chargePointId: string | undefined, locationId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: StopTransactionPayload) => stopTransaction(chargePointId!, payload),
    onSuccess: () => {
      if (chargePointId) {
        queryClient.invalidateQueries({ queryKey: ['chargers', 'detail', chargePointId] });
      }
      if (locationId) {
        queryClient.invalidateQueries({ queryKey: chargersQueryKey(locationId) });
      }
    },
  });
}
