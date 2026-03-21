import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';
import type { ChargingProfileResponse, EvaluatedLimitResponse } from '@/types/ocpp';

export function useChargingProfiles(chargePointId: string | undefined) {
  return useQuery<ChargingProfileResponse[]>({
    queryKey: ['charging-profiles', chargePointId],
    queryFn: () => apiFetch(`/api/chargers/${chargePointId}/charging-profiles`),
    enabled: !!chargePointId,
  });
}

export function useEvaluatedLimit(
  chargePointId: string | undefined,
  connectorId: number,
) {
  return useQuery<EvaluatedLimitResponse>({
    queryKey: ['charging-profiles-evaluate', chargePointId, connectorId],
    queryFn: () =>
      apiFetch(`/api/chargers/${chargePointId}/charging-profiles/evaluate?connector_id=${connectorId}`),
    enabled: !!chargePointId,
    refetchInterval: 5000,
  });
}
