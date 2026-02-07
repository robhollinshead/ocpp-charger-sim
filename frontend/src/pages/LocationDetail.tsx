import { useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { useLocations, useDeleteLocation } from '@/api/locations';
import { useChargers, useConnectCharger, useDisconnectCharger } from '@/api/chargers';
import { ChargerCard } from '@/components/ChargerCard';
import { CreateChargerDialog } from '@/components/CreateChargerDialog';
import { Breadcrumbs } from '@/components/Breadcrumbs';
import { StatusBadge } from '@/components/StatusBadge';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { MapPin, Zap, Play, Trash2, Plus, Link2, Link2Off } from 'lucide-react';
import { toast } from "sonner";

export default function LocationDetail() {
  const { locationId } = useParams();
  const navigate = useNavigate();
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [createChargerOpen, setCreateChargerOpen] = useState(false);
  const { data: locations = [] } = useLocations();
  const { data: locationChargers = [], isLoading: chargersLoading } = useChargers(locationId);
  const deleteLocation = useDeleteLocation();
  const connectCharger = useConnectCharger(locationId);
  const disconnectCharger = useDisconnectCharger(locationId);
  const location = locations.find(l => l.id === locationId);
  const anyConnectPending = connectCharger.isPending;
  const anyDisconnectPending = disconnectCharger.isPending;
  const connectedChargers = locationChargers.filter(c => c.connected);

  async function handleDeleteLocation() {
    if (!locationId) return;
    try {
      await deleteLocation.mutateAsync(locationId);
      toast.success('Location deleted');
      navigate('/');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to delete location');
    } finally {
      setDeleteDialogOpen(false);
    }
  }

  if (!location) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-xl font-semibold mb-2">Location not found</h1>
          <Link to="/" className="text-primary hover:underline">Return to locations</Link>
        </div>
      </div>
    );
  }

  const connectedCount = locationChargers.filter(c => c.connected).length;

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-6xl mx-auto p-6">
        <Breadcrumbs items={[
          { label: 'Locations', href: '/' },
          { label: location.name }
        ]} />
        
        <div className="mt-6 mb-8">
          <div className="flex items-start justify-between">
            <div>
              <h1 className="text-2xl font-bold text-foreground mb-2">{location.name}</h1>
              <div className="flex items-center gap-1.5 text-muted-foreground">
                <MapPin className="h-4 w-4" />
                {location.address}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button>
                <Play className="h-4 w-4 mr-1" />
                Run Scenario
              </Button>
              <Button
                variant="outline"
                className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                onClick={() => setDeleteDialogOpen(true)}
                disabled={deleteLocation.isPending}
              >
                <Trash2 className="h-4 w-4 mr-1" />
                Delete location
              </Button>
            </div>
          </div>
        </div>

        <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete location?</AlertDialogTitle>
              <AlertDialogDescription>
                This will permanently delete &quot;{location.name}&quot;. This action cannot be undone.
                {locationChargers.length > 0 && (
                  <>
                    {' '}
                    Deleting this location will also permanently delete the {locationChargers.length} charger{locationChargers.length === 1 ? '' : 's'} at this location.
                  </>
                )}
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction
                onClick={(e) => {
                  e.preventDefault();
                  handleDeleteLocation();
                }}
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              >
                {deleteLocation.isPending ? 'Deleting…' : 'Delete'}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        <div className="grid gap-4 md:grid-cols-2 mb-8">
          <Card className="bg-card border-border">
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-lg bg-primary/20 flex items-center justify-center">
                  <Zap className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <p className="text-2xl font-bold">{locationChargers.length}</p>
                  <p className="text-sm text-muted-foreground">Total Chargers</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card className="bg-card border-border">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-2xl font-bold">{connectedCount}</p>
                  <p className="text-sm text-muted-foreground">Connected</p>
                </div>
                <StatusBadge status={connectedCount > 0 ? 'Available' : 'Offline'} size="sm" />
              </div>
            </CardContent>
          </Card>
        </div>

        <CreateChargerDialog
          locationId={locationId}
          open={createChargerOpen}
          onOpenChange={setCreateChargerOpen}
        />

        <div className="mb-4 flex items-center justify-between flex-wrap gap-2">
          <h2 className="text-lg font-semibold">Chargers</h2>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => locationChargers.forEach(c => connectCharger.mutate(c.id))}
              disabled={chargersLoading || anyConnectPending || locationChargers.length === 0}
            >
              <Link2 className="h-4 w-4 mr-1" />
              {anyConnectPending ? 'Connecting…' : 'Connect all'}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => connectedChargers.forEach(c => disconnectCharger.mutate(c.id))}
              disabled={anyDisconnectPending || connectedChargers.length === 0}
            >
              <Link2Off className="h-4 w-4 mr-1" />
              {anyDisconnectPending ? 'Disconnecting…' : 'Disconnect all'}
            </Button>
            <Button onClick={() => setCreateChargerOpen(true)}>
              <Plus className="h-4 w-4 mr-1" />
              Add charger
            </Button>
          </div>
        </div>

        {chargersLoading ? (
          <p className="text-muted-foreground">Loading chargers…</p>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {locationChargers.map(charger => (
              <ChargerCard key={charger.id} charger={charger} locationId={locationId} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
