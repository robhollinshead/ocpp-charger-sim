import { Link } from 'react-router-dom';
import { useConnectCharger, useDisconnectCharger } from '@/api/chargers';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { StatusBadge } from './StatusBadge';
import { Plug, Link2, Link2Off } from 'lucide-react';
import type { Charger, ChargerStatus } from '@/types/ocpp';

interface ChargerCardProps {
  charger: Charger;
  locationId: string | undefined;
}

export function ChargerCard({ charger, locationId }: ChargerCardProps) {
  const status: ChargerStatus = charger.connected ? 'Available' : 'Offline';
  const connectCharger = useConnectCharger(locationId);
  const disconnectCharger = useDisconnectCharger(locationId);
  const isConnecting = connectCharger.isPending && connectCharger.variables === charger.id;
  const isDisconnecting = disconnectCharger.isPending && disconnectCharger.variables === charger.id;

  function handleConnect(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    connectCharger.mutate(charger.id);
  }

  function handleDisconnect(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    disconnectCharger.mutate(charger.id);
  }

  return (
    <Link to={`/location/${charger.location_id}/charger/${charger.id}`}>
      <Card className="bg-card border-border hover:border-primary/50 hover:bg-card/80 transition-all cursor-pointer group">
        <CardContent className="p-5">
          <div className="flex items-start justify-between mb-3">
            <div>
              <h3 className="font-semibold text-lg text-foreground group-hover:text-primary transition-colors">
                {charger.charger_name}
              </h3>
              <p className="text-sm text-muted-foreground font-mono">{charger.charge_point_id}</p>
            </div>
            <StatusBadge status={status} />
          </div>

          <div className="space-y-2 mb-4">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <span className="font-mono text-xs bg-secondary px-2 py-0.5 rounded">
                OCPP {charger.ocpp_version}
              </span>
              <span className="font-mono text-xs bg-secondary px-2 py-0.5 rounded">
                {charger.evse_count} EVSE{charger.evse_count !== 1 ? 's' : ''}
              </span>
            </div>
          </div>

          <div className="flex items-center justify-between pt-3 border-t border-border gap-2">
            <div className="flex items-center gap-3 min-w-0">
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground truncate" title={charger.connection_url}>
                <Plug className="h-3.5 w-3.5 shrink-0" />
                <span className="truncate">{charger.connection_url}</span>
              </div>
            </div>
            <div className="flex items-center gap-1.5 shrink-0" onClick={(e) => e.stopPropagation()}>
              {charger.connected ? (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={handleDisconnect}
                  disabled={isDisconnecting}
                >
                  <Link2Off className="h-3.5 w-3.5 mr-1" />
                  {isDisconnecting ? 'Disconnecting…' : 'Disconnect'}
                </Button>
              ) : (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={handleConnect}
                  disabled={isConnecting}
                >
                  <Link2 className="h-3.5 w-3.5 mr-1" />
                  {isConnecting ? 'Connecting…' : 'Connect'}
                </Button>
              )}
            </div>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}
