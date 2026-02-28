import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';

const API_PREFIX = '/api';

export interface ScenarioRunResponse {
  location_id: string;
  scenario_type: string;
  duration_minutes: number;
  started_at: string;
  total_pairs: number;
  completed_pairs: number;
  failed_pairs: number;
  offline_charger_ids: string[];
  status: 'running' | 'completed' | 'cancelled';
}

export interface StopAllChargingResponse {
  stopped: number;
  errors: number;
}

export async function startRushPeriod(
  locationId: string,
  durationMinutes: number
): Promise<ScenarioRunResponse> {
  return apiFetch<ScenarioRunResponse>(
    `${API_PREFIX}/locations/${locationId}/scenarios/rush-period`,
    {
      method: 'POST',
      body: JSON.stringify({ duration_minutes: durationMinutes }),
    }
  );
}

export async function fetchActiveScenario(
  locationId: string
): Promise<ScenarioRunResponse | null> {
  return apiFetch<ScenarioRunResponse | null>(
    `${API_PREFIX}/locations/${locationId}/scenarios/active`
  );
}

export async function cancelScenario(locationId: string): Promise<void> {
  await apiFetch(`${API_PREFIX}/locations/${locationId}/scenarios/active`, {
    method: 'DELETE',
  });
}

export async function stopAllCharging(locationId: string): Promise<StopAllChargingResponse> {
  return apiFetch<StopAllChargingResponse>(
    `${API_PREFIX}/locations/${locationId}/scenarios/stop-all-charging`,
    { method: 'POST' }
  );
}

function activeScenarioQueryKey(locationId: string) {
  return ['scenarios', 'active', locationId] as const;
}

export function useActiveScenario(
  locationId: string | undefined,
  refetchInterval?: number | false
) {
  return useQuery({
    queryKey: activeScenarioQueryKey(locationId ?? ''),
    queryFn: () => fetchActiveScenario(locationId!),
    enabled: !!locationId,
    refetchInterval,
  });
}

export function useStartRushPeriod(locationId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (durationMinutes: number) => startRushPeriod(locationId!, durationMinutes),
    onSuccess: () => {
      if (locationId) {
        queryClient.invalidateQueries({ queryKey: activeScenarioQueryKey(locationId) });
      }
    },
  });
}

export function useStopScenario(locationId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => cancelScenario(locationId!),
    onSuccess: () => {
      if (locationId) {
        queryClient.invalidateQueries({ queryKey: activeScenarioQueryKey(locationId) });
      }
    },
  });
}

export function useStopAllCharging(locationId: string | undefined) {
  return useMutation({
    mutationFn: () => stopAllCharging(locationId!),
  });
}
