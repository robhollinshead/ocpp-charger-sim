import { useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { useLocations, useDeleteLocation } from '@/api/locations';
import { useChargers, useConnectCharger, useDisconnectCharger } from '@/api/chargers';
import { useVehicles, useDeleteVehicle } from '@/api/vehicles';
import { ChargerCard } from '@/components/ChargerCard';
import { CreateChargerDialog } from '@/components/CreateChargerDialog';
import { AddVehicleDialog } from '@/components/AddVehicleDialog';
import { ImportChargersModal } from '@/components/ImportChargersModal';
import { ImportVehiclesModal } from '@/components/ImportVehiclesModal';
import { Breadcrumbs } from '@/components/Breadcrumbs';
import { ConnectionBadge } from '@/components/ConnectionBadge';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
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
import { MapPin, Zap, Play, Trash2, Plus, Link2, Link2Off, Car, Upload } from 'lucide-react';
import { toast } from 'sonner';
import type { Vehicle } from '@/types/ocpp';
import { ScenariosTab } from '@/components/location/ScenariosTab';

export default function LocationDetail() {
  const { locationId } = useParams();
  const navigate = useNavigate();
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [createChargerOpen, setCreateChargerOpen] = useState(false);
  const [createVehicleOpen, setCreateVehicleOpen] = useState(false);
  const [importChargersOpen, setImportChargersOpen] = useState(false);
  const [importVehiclesOpen, setImportVehiclesOpen] = useState(false);
  const [vehicleToDelete, setVehicleToDelete] = useState<Vehicle | null>(null);

  const { data: locations = [] } = useLocations();
  const { data: locationChargers = [], isLoading: chargersLoading } = useChargers(locationId);
  const { data: vehicles = [], isLoading: vehiclesLoading } = useVehicles(locationId);
  const deleteLocation = useDeleteLocation();
  const connectCharger = useConnectCharger(locationId);
  const disconnectCharger = useDisconnectCharger(locationId);
  const deleteVehicle = useDeleteVehicle(locationId);
  const location = locations.find((l) => l.id === locationId);
  const anyConnectPending = connectCharger.isPending;
  const anyDisconnectPending = disconnectCharger.isPending;
  const connectedChargers = locationChargers.filter((c) => c.connected);

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

  async function handleDeleteVehicle() {
    if (!locationId || !vehicleToDelete) return;
    try {
      await deleteVehicle.mutateAsync(vehicleToDelete.id);
      toast.success('Vehicle deleted');
      setVehicleToDelete(null);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to delete vehicle');
    }
  }

  if (!location) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-xl font-semibold mb-2">Location not found</h1>
          <Link to="/" className="text-primary hover:underline">
            Return to locations
          </Link>
        </div>
      </div>
    );
  }

  const connectedCount = locationChargers.filter((c) => c.connected).length;

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-6xl mx-auto p-6">
        <Breadcrumbs items={[{ label: 'Locations', href: '/' }, { label: location.name }]} />

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
                    Deleting this location will also permanently delete the {locationChargers.length}{' '}
                    charger{locationChargers.length === 1 ? '' : 's'} at this location.
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

        <AlertDialog
          open={vehicleToDelete !== null}
          onOpenChange={(open) => !open && setVehicleToDelete(null)}
        >
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete vehicle?</AlertDialogTitle>
              <AlertDialogDescription>
                This will permanently remove {vehicleToDelete?.name ?? 'this vehicle'}. This action
                cannot be undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction
                onClick={(e) => {
                  e.preventDefault();
                  handleDeleteVehicle();
                }}
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                disabled={deleteVehicle.isPending}
              >
                {deleteVehicle.isPending ? 'Deleting…' : 'Delete'}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        <CreateChargerDialog
          locationId={locationId}
          open={createChargerOpen}
          onOpenChange={setCreateChargerOpen}
        />
        <AddVehicleDialog
          locationId={locationId}
          open={createVehicleOpen}
          onOpenChange={setCreateVehicleOpen}
        />
        <ImportChargersModal
          locationId={locationId}
          open={importChargersOpen}
          onOpenChange={setImportChargersOpen}
        />
        <ImportVehiclesModal
          locationId={locationId}
          open={importVehiclesOpen}
          onOpenChange={setImportVehiclesOpen}
        />

        <Tabs defaultValue="chargers" className="space-y-4">
          <TabsList>
            <TabsTrigger value="chargers" className="gap-2">
              <Zap className="h-4 w-4" />
              Chargers
            </TabsTrigger>
            <TabsTrigger value="vehicles" className="gap-2">
              <Car className="h-4 w-4" />
              Vehicles
            </TabsTrigger>
            <TabsTrigger value="scenarios" className="gap-2">
              <Play className="h-4 w-4" />
              Scenarios
            </TabsTrigger>
          </TabsList>

          <TabsContent value="chargers" className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2 mb-6">
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
                    <ConnectionBadge
                      connected={connectedCount > 0}
                      size="sm"
                    />
                  </div>
                </CardContent>
              </Card>
            </div>

            <div className="mb-4 flex items-center justify-between flex-wrap gap-2">
              <h2 className="text-lg font-semibold">Chargers</h2>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => locationChargers.forEach((c) => connectCharger.mutate(c.id))}
                  disabled={
                    chargersLoading || anyConnectPending || locationChargers.length === 0
                  }
                >
                  <Link2 className="h-4 w-4 mr-1" />
                  {anyConnectPending ? 'Connecting…' : 'Connect all'}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    connectedChargers.forEach((c) => disconnectCharger.mutate(c.id))
                  }
                  disabled={anyDisconnectPending || connectedChargers.length === 0}
                >
                  <Link2Off className="h-4 w-4 mr-1" />
                  {anyDisconnectPending ? 'Disconnecting…' : 'Disconnect all'}
                </Button>
                <Button variant="outline" size="sm" onClick={() => setImportChargersOpen(true)}>
                  <Upload className="h-4 w-4 mr-1" />
                  Import Chargers
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
                {locationChargers.map((charger) => (
                  <ChargerCard
                    key={charger.id}
                    charger={charger}
                    locationId={locationId}
                  />
                ))}
              </div>
            )}
          </TabsContent>

          <TabsContent value="vehicles" className="space-y-4">
            <div className="mb-4 flex items-center justify-between flex-wrap gap-2">
              <h2 className="text-lg font-semibold">Vehicles</h2>
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" onClick={() => setImportVehiclesOpen(true)}>
                  <Upload className="h-4 w-4 mr-1" />
                  Import Vehicles
                </Button>
                <Button onClick={() => setCreateVehicleOpen(true)}>
                  <Plus className="h-4 w-4 mr-1" />
                  Add Vehicle
                </Button>
              </div>
            </div>

            {vehiclesLoading ? (
              <p className="text-muted-foreground">Loading vehicles…</p>
            ) : vehicles.length === 0 ? (
              <p className="text-muted-foreground">No vehicles at this location.</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>idTag</TableHead>
                    <TableHead className="text-right">Battery (kWh)</TableHead>
                    <TableHead className="w-[80px]"></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {vehicles.map((vehicle) => (
                    <TableRow key={vehicle.id}>
                      <TableCell className="font-medium">{vehicle.name}</TableCell>
                      <TableCell>{vehicle.idTags?.length ? vehicle.idTags.join(', ') : '—'}</TableCell>
                      <TableCell className="text-right">
                        {vehicle.battery_capacity_kWh}
                      </TableCell>
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="text-destructive hover:text-destructive hover:bg-destructive/10"
                          onClick={() => setVehicleToDelete(vehicle)}
                          disabled={deleteVehicle.isPending}
                          aria-label={`Delete ${vehicle.name}`}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </TabsContent>

          <TabsContent value="scenarios" className="space-y-4">
            <ScenariosTab locationId={locationId} />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
