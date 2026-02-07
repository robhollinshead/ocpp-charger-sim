import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { Location, LocationCreate, LocationResponse } from '@/types/ocpp';
import { apiFetch } from '@/lib/api';

const LOCATIONS_QUERY_KEY = ['locations'] as const;

function mapResponseToLocation(r: LocationResponse): Location {
  return {
    id: r.id,
    name: r.name,
    address: r.address,
    chargerCount: r.charger_count,
  };
}

const API_PREFIX = '/api';

export async function fetchLocations(): Promise<Location[]> {
  const data = await apiFetch<LocationResponse[]>(`${API_PREFIX}/locations`);
  return data.map(mapResponseToLocation);
}

export async function createLocation(payload: LocationCreate): Promise<Location> {
  const data = await apiFetch<LocationResponse>(`${API_PREFIX}/locations`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  return mapResponseToLocation(data);
}

export async function deleteLocation(id: string): Promise<void> {
  await apiFetch(`${API_PREFIX}/locations/${id}`, { method: 'DELETE' });
}

export function useLocations() {
  return useQuery({
    queryKey: LOCATIONS_QUERY_KEY,
    queryFn: fetchLocations,
  });
}

export function useCreateLocation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createLocation,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: LOCATIONS_QUERY_KEY });
    },
  });
}

export function useDeleteLocation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteLocation,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: LOCATIONS_QUERY_KEY });
    },
  });
}
