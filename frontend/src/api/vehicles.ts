import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { Vehicle, VehicleCreate, VehicleResponse } from '@/types/ocpp';
import { apiFetch } from '@/lib/api';

const API_PREFIX = '/api';

function mapResponseToVehicle(r: VehicleResponse): Vehicle {
  return {
    id: r.id,
    name: r.name,
    idTags: r.idTags ?? [],
    battery_capacity_kWh: r.battery_capacity_kWh,
    location_id: r.location_id,
  };
}

export async function fetchVehiclesByLocation(locationId: string): Promise<Vehicle[]> {
  const data = await apiFetch<VehicleResponse[]>(`${API_PREFIX}/locations/${locationId}/vehicles`);
  return data.map(mapResponseToVehicle);
}

export async function createVehicle(locationId: string, payload: VehicleCreate): Promise<Vehicle> {
  const data = await apiFetch<VehicleResponse>(`${API_PREFIX}/locations/${locationId}/vehicles`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  return mapResponseToVehicle(data);
}

export async function deleteVehicle(locationId: string, vehicleId: string): Promise<void> {
  await apiFetch<void>(`${API_PREFIX}/locations/${locationId}/vehicles/${vehicleId}`, {
    method: 'DELETE',
  });
}

export function vehiclesQueryKey(locationId: string) {
  return ['vehicles', locationId] as const;
}

export function useVehicles(locationId: string | undefined) {
  return useQuery({
    queryKey: vehiclesQueryKey(locationId ?? ''),
    queryFn: () => fetchVehiclesByLocation(locationId!),
    enabled: !!locationId,
  });
}

export function useCreateVehicle(locationId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: VehicleCreate) => createVehicle(locationId!, payload),
    onSuccess: () => {
      if (locationId) {
        queryClient.invalidateQueries({ queryKey: vehiclesQueryKey(locationId) });
      }
    },
  });
}

export function useDeleteVehicle(locationId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (vehicleId: string) => deleteVehicle(locationId!, vehicleId),
    onSuccess: () => {
      if (locationId) {
        queryClient.invalidateQueries({ queryKey: vehiclesQueryKey(locationId) });
      }
    },
  });
}
