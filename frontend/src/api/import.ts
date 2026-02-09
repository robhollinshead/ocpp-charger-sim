import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { ChargerResponse } from '@/types/ocpp';
import type { ImportResult } from '@/types/ocpp';
import type { VehicleResponse } from '@/types/ocpp';
import { getApiBaseUrl } from '@/lib/api';
import { apiFetchFormData } from '@/lib/api';
import { chargersQueryKey } from '@/api/chargers';
import { vehiclesQueryKey } from '@/api/vehicles';

const API_PREFIX = '/api';

export async function importChargers(
  locationId: string,
  file: File,
  defaultConnectionUrl?: string
): Promise<ImportResult<ChargerResponse>> {
  const formData = new FormData();
  formData.append('file', file);
  if (defaultConnectionUrl?.trim()) {
    formData.append('default_connection_url', defaultConnectionUrl.trim());
  }
  return apiFetchFormData<ImportResult<ChargerResponse>>(
    `${API_PREFIX}/locations/${locationId}/import/chargers`,
    formData
  );
}

export async function importVehicles(
  locationId: string,
  file: File
): Promise<ImportResult<VehicleResponse>> {
  const formData = new FormData();
  formData.append('file', file);
  return apiFetchFormData<ImportResult<VehicleResponse>>(
    `${API_PREFIX}/locations/${locationId}/import/vehicles`,
    formData
  );
}

export function getChargersCsvTemplateUrl(): string {
  return `${getApiBaseUrl()}${API_PREFIX}/import/templates/chargers.csv`;
}

export function getChargersJsonTemplateUrl(): string {
  return `${getApiBaseUrl()}${API_PREFIX}/import/templates/chargers.json`;
}

export function getVehiclesCsvTemplateUrl(): string {
  return `${getApiBaseUrl()}${API_PREFIX}/import/templates/vehicles.csv`;
}

export function getVehiclesJsonTemplateUrl(): string {
  return `${getApiBaseUrl()}${API_PREFIX}/import/templates/vehicles.json`;
}

export interface ImportChargersPayload {
  file: File;
  defaultConnectionUrl?: string;
}

export function useImportChargers(locationId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ file, defaultConnectionUrl }: ImportChargersPayload) =>
      importChargers(locationId!, file, defaultConnectionUrl),
    onSuccess: () => {
      if (locationId) {
        queryClient.invalidateQueries({ queryKey: chargersQueryKey(locationId) });
        queryClient.invalidateQueries({ queryKey: ['locations'] });
      }
    },
  });
}

export function useImportVehicles(locationId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => importVehicles(locationId!, file),
    onSuccess: () => {
      if (locationId) {
        queryClient.invalidateQueries({ queryKey: vehiclesQueryKey(locationId) });
      }
    },
  });
}
