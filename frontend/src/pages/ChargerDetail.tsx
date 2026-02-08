import { useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { useLocations } from '@/api/locations';
import { useChargerDetail, useDeleteCharger, useConnectCharger, useDisconnectCharger } from '@/api/chargers';
import { Breadcrumbs } from '@/components/Breadcrumbs';
import { StatusBadge } from '@/components/StatusBadge';
import { ChargerDetailsEdit } from '@/components/ChargerDetailsEdit';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent } from '@/components/ui/card';
import { ConfigurationTab } from '@/components/charger/ConfigurationTab';
import { LogsTab } from '@/components/charger/LogsTab';
import { TransactionsTab } from '@/components/charger/TransactionsTab';
import { ScenariosTab } from '@/components/charger/ScenariosTab';
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
import { Button } from '@/components/ui/button';
import { Settings, FileText, Zap, Play, Plug, Trash2, Link2, Link2Off } from 'lucide-react';
import { toast } from 'sonner';
import type { ChargerStatus } from '@/types/ocpp';

export default function ChargerDetail() {
  const { locationId, chargerId } = useParams();
  const navigate = useNavigate();
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const { data: locations = [] } = useLocations();
  const { data: charger, isLoading: chargerLoading, error: chargerError } = useChargerDetail(chargerId);
  const deleteCharger = useDeleteCharger(locationId);
  const connectCharger = useConnectCharger(locationId);
  const disconnectCharger = useDisconnectCharger(locationId);
  const location = locations.find((l) => l.id === locationId);

  async function handleDeleteCharger() {
    if (!chargerId || !locationId) return;
    try {
      await deleteCharger.mutateAsync(chargerId);
      toast.success('Charger deleted');
      navigate(`/location/${locationId}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to delete charger');
    } finally {
      setDeleteDialogOpen(false);
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

  if (chargerLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <p className="text-muted-foreground">Loading charger…</p>
      </div>
    );
  }

  if (chargerError || !charger) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-xl font-semibold mb-2">Charger not found</h1>
          <Link to={`/location/${locationId}`} className="text-primary hover:underline">
            Return to location
          </Link>
        </div>
      </div>
    );
  }

  const status: ChargerStatus = charger.connected ? 'Available' : 'Offline';

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-6xl mx-auto p-6">
        <Breadcrumbs
          items={[
            { label: 'Locations', href: '/' },
            { label: location.name, href: `/location/${locationId}` },
            { label: charger.charger_name },
          ]}
        />

        <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete charger?</AlertDialogTitle>
              <AlertDialogDescription>
                This will permanently delete &quot;{charger.charger_name}&quot; ({charger.charge_point_id}). This action cannot be undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction
                onClick={(e) => {
                  e.preventDefault();
                  handleDeleteCharger();
                }}
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              >
                {deleteCharger.isPending ? 'Deleting…' : 'Delete'}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        <div className="mt-6 mb-6">
          <div className="flex items-start justify-between flex-wrap gap-2">
            <div>
              <div className="flex items-center gap-3 mb-2">
                <h1 className="text-2xl font-bold text-foreground">{charger.charger_name}</h1>
                <StatusBadge status={status} />
              </div>
              <p className="text-muted-foreground font-mono text-sm">{charger.charge_point_id}</p>
            </div>
            <div className="flex items-center gap-2">
              {charger.connected ? (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => disconnectCharger.mutate(charger.id)}
                  disabled={disconnectCharger.isPending}
                >
                  <Link2Off className="h-4 w-4 mr-1" />
                  {disconnectCharger.isPending ? 'Disconnecting…' : 'Disconnect'}
                </Button>
              ) : (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => connectCharger.mutate(charger.id)}
                  disabled={connectCharger.isPending}
                >
                  <Link2 className="h-4 w-4 mr-1" />
                  {connectCharger.isPending ? 'Connecting…' : 'Connect'}
                </Button>
              )}
              <Button
                variant="outline"
                className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                onClick={() => setDeleteDialogOpen(true)}
                disabled={deleteCharger.isPending}
              >
                <Trash2 className="h-4 w-4 mr-1" />
                Delete charger
              </Button>
            </div>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-3 mb-6">
          <Card className="bg-card border-border">
            <CardContent className="p-4">
              <p className="text-xs text-muted-foreground mb-1">OCPP Version</p>
              <p className="font-mono font-medium">{charger.ocpp_version}</p>
            </CardContent>
          </Card>
          <Card className="bg-card border-border">
            <CardContent className="p-4">
              <p className="text-xs text-muted-foreground mb-1">EVSEs</p>
              <div className="flex items-center gap-2">
                {charger.evses.map((evse) => (
                  <span key={evse.evse_id} className="flex items-center gap-1 text-sm">
                    <Plug className="h-3.5 w-3.5 text-muted-foreground" />
                    EVSE {evse.evse_id} ({evse.state})
                  </span>
                ))}
              </div>
            </CardContent>
          </Card>
          <Card className="bg-card border-border">
            <CardContent className="p-4">
              <p className="text-xs text-muted-foreground mb-1">Connection</p>
              <p className="text-sm truncate" title={charger.connection_url}>
                {charger.connected ? 'Connected' : 'Disconnected'}
              </p>
            </CardContent>
          </Card>
        </div>

        <Tabs defaultValue="config" className="space-y-6">
          <TabsList className="bg-secondary/50 border border-border p-1">
            <TabsTrigger
              value="config"
              className="data-[state=active]:bg-card data-[state=active]:text-foreground gap-2"
            >
              <Settings className="h-4 w-4" />
              Configuration
            </TabsTrigger>
            <TabsTrigger
              value="logs"
              className="data-[state=active]:bg-card data-[state=active]:text-foreground gap-2"
            >
              <FileText className="h-4 w-4" />
              OCPP Logs
            </TabsTrigger>
            <TabsTrigger
              value="transactions"
              className="data-[state=active]:bg-card data-[state=active]:text-foreground gap-2"
            >
              <Zap className="h-4 w-4" />
              Transactions
            </TabsTrigger>
            <TabsTrigger
              value="scenarios"
              className="data-[state=active]:bg-card data-[state=active]:text-foreground gap-2"
            >
              <Play className="h-4 w-4" />
              Scenarios
            </TabsTrigger>
          </TabsList>

          <TabsContent value="config" className="space-y-6">
            <ChargerDetailsEdit charger={charger} locationId={locationId!} />
            <ConfigurationTab charger={charger} />
          </TabsContent>
          <TabsContent value="logs">
            <LogsTab chargePointId={chargerId} />
          </TabsContent>
          <TabsContent value="transactions">
            <TransactionsTab chargePointId={charger.id} locationId={locationId!} />
          </TabsContent>
          <TabsContent value="scenarios">
            <ScenariosTab />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
