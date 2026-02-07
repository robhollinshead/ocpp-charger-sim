import { useState } from 'react';
import { LocationCard } from '@/components/LocationCard';
import { Breadcrumbs } from '@/components/Breadcrumbs';
import { CreateLocationDialog } from '@/components/CreateLocationDialog';
import { Button } from '@/components/ui/button';
import { MapPin, Plus } from 'lucide-react';
import { useLocations } from '@/api/locations';

export default function LocationList() {
  const [createOpen, setCreateOpen] = useState(false);
  const { data: locations = [], isLoading, error } = useLocations();

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-6xl mx-auto p-6">
        <Breadcrumbs items={[{ label: 'Locations' }]} />

        <div className="mt-6 mb-8">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <div className="flex items-center gap-3 mb-2">
                <div className="h-10 w-10 rounded-lg bg-primary/20 flex items-center justify-center">
                  <MapPin className="h-5 w-5 text-primary" />
                </div>
                <h1 className="text-2xl font-bold text-foreground">Charging Locations</h1>
              </div>
              <p className="text-muted-foreground">
                Select a location to view and manage its chargers
              </p>
            </div>
            <Button onClick={() => setCreateOpen(true)}>
              <Plus className="h-4 w-4" />
              Create location
            </Button>
          </div>
        </div>

        {isLoading && (
          <p className="text-muted-foreground">Loading locations…</p>
        )}
        {error && (
          <p className="text-destructive">
            Failed to load locations. Check that the backend is running and VITE_API_URL is set.
          </p>
        )}
        {!isLoading && !error && (
          <div className="grid gap-4 md:grid-cols-2">
            {locations.map(location => (
              <LocationCard key={location.id} location={location} />
            ))}
          </div>
        )}

        <CreateLocationDialog open={createOpen} onOpenChange={setCreateOpen} />
      </div>
    </div>
  );
}
