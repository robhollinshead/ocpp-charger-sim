import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Play, Square, Zap, Clock, Battery } from 'lucide-react';
import { format } from 'date-fns';
import { toast } from 'sonner';
import {
  useChargerDetail,
  useStartTransaction,
  useStopTransaction,
} from '@/api/chargers';
import { useVehicles } from '@/api/vehicles';
import type { EvseStatusResponse } from '@/types/ocpp';

const CUSTOM_IDTAG_VALUE = '__custom__';

const CHARGER_DETAIL_POLL_MS = 5000;

interface TransactionsTabProps {
  chargePointId: string;
  locationId: string;
}

function evseToActiveTx(evse: EvseStatusResponse) {
  return {
    id: String(evse.transaction_id),
    connectorId: evse.evse_id,
    idTag: evse.id_tag ?? '',
    startTime: evse.session_start_time ?? new Date().toISOString(),
  };
}

export function TransactionsTab({ chargePointId, locationId }: TransactionsTabProps) {
  const [idTag, setIdTag] = useState('');
  const [connectorId, setConnectorId] = useState('1');

  const { data: vehicles = [] } = useVehicles(locationId);
  const idTagOptions = vehicles.flatMap((v) =>
    v.idTags.map((idTagVal) => ({ idTag: idTagVal, vehicleName: v.name }))
  );

  const { data: charger, refetch: refetchCharger } = useChargerDetail(chargePointId, {
    refetchInterval: (query) => {
      const data = query.state.data;
      const hasActive = data?.evses?.some((e) => e.transaction_id != null);
      return hasActive ? CHARGER_DETAIL_POLL_MS : false;
    },
  });

  const startTx = useStartTransaction(chargePointId, locationId);
  const stopTx = useStopTransaction(chargePointId, locationId);

  const activeTransactions =
    charger?.evses
      ?.filter((e) => e.transaction_id != null)
      .map(evseToActiveTx) ?? [];

  const handleStartTransaction = () => {
    if (!idTag.trim()) {
      toast.error('Please enter an ID Tag');
      return;
    }
    const connector = parseInt(connectorId, 10);
    if (isNaN(connector) || connector < 1) {
      toast.error('Invalid connector');
      return;
    }
    startTx.mutate(
      { connector_id: connector, id_tag: idTag.trim() },
      {
        onSuccess: () => {
          toast.success(`Transaction started on connector ${connector}`);
          void refetchCharger();
        },
        onError: (err) => {
          const msg = err instanceof Error ? err.message : 'Failed to start transaction';
          try {
            const parsed = JSON.parse(msg) as { detail?: string };
            toast.error(parsed.detail ?? msg);
          } catch {
            toast.error(msg);
          }
        },
      }
    );
  };

  const handleStopTransaction = (connectorIdToStop: number) => {
    stopTx.mutate(
      { connector_id: connectorIdToStop },
      {
        onSuccess: () => {
          toast.success(`Transaction stopped on connector ${connectorIdToStop}`);
          void refetchCharger();
        },
        onError: (err) => {
          const msg = err instanceof Error ? err.message : 'Failed to stop transaction';
          try {
            const parsed = JSON.parse(msg) as { detail?: string };
            toast.error(parsed.detail ?? msg);
          } catch {
            toast.error(msg);
          }
        },
      }
    );
  };

  const isStartDisabled =
    !charger?.connected ||
    startTx.isPending ||
    !idTag.trim();

  return (
    <div className="space-y-6">
      <Card className="bg-card border-border">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Play className="h-4 w-4 text-primary" />
            Start New Transaction
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-end gap-4">
            <div className="flex-1 min-w-[200px] space-y-2">
              <label className="text-sm text-muted-foreground" id="idtag-label">
                ID Tag (from list or custom)
              </label>
              <div className="flex gap-2">
                <Select
                  value={idTagOptions.some((o) => o.idTag === idTag) ? idTag : CUSTOM_IDTAG_VALUE}
                  onValueChange={(value) => {
                    if (value === CUSTOM_IDTAG_VALUE) {
                      setIdTag('');
                    } else {
                      setIdTag(value);
                    }
                  }}
                  aria-labelledby="idtag-label"
                >
                  <SelectTrigger className="w-[200px] shrink-0 bg-secondary border-border">
                    <SelectValue placeholder="Choose or type below" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={CUSTOM_IDTAG_VALUE}>Enter custom idTag…</SelectItem>
                    {idTagOptions.map((o) => (
                      <SelectItem key={`${o.idTag}-${o.vehicleName}`} value={o.idTag}>
                        {o.idTag} — {o.vehicleName}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Input
                  placeholder="Enter RFID tag or token..."
                  value={idTag}
                  onChange={(e) => setIdTag(e.target.value)}
                  className="flex-1 bg-secondary border-border font-mono"
                  aria-label="ID Tag value"
                />
              </div>
            </div>
            <div className="w-24 space-y-2">
              <label className="text-sm text-muted-foreground">Connector</label>
              <Input
                type="number"
                min="1"
                value={connectorId}
                onChange={(e) => setConnectorId(e.target.value)}
                className="bg-secondary border-border"
              />
            </div>
            <Button
              onClick={handleStartTransaction}
              className="h-10"
              disabled={isStartDisabled}
            >
              <Zap className="h-4 w-4 mr-1" />
              {startTx.isPending ? 'Starting…' : 'Start Charging'}
            </Button>
          </div>
          {!charger?.connected && (
            <p className="text-sm text-muted-foreground mt-2">
              Connect the charger to CSMS to start a transaction.
            </p>
          )}
        </CardContent>
      </Card>

      {activeTransactions.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-sm font-medium text-muted-foreground">Active Transactions</h3>
          {activeTransactions.map((tx) => (
            <Card key={tx.id} className="bg-card border-warning/30">
              <CardContent className="p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className="h-10 w-10 rounded-full bg-warning/20 flex items-center justify-center">
                      <Battery className="h-5 w-5 text-warning animate-pulse-glow" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-medium">{tx.id}</span>
                        <Badge className="bg-warning/20 text-warning border-warning/30">Active</Badge>
                      </div>
                      <div className="flex items-center gap-3 text-sm text-muted-foreground mt-1">
                        <span>Connector {tx.connectorId}</span>
                        <span>•</span>
                        <span className="font-mono">{tx.idTag || '—'}</span>
                        <span>•</span>
                        <span className="flex items-center gap-1">
                          <Clock className="h-3 w-3" />
                          {format(new Date(tx.startTime), 'HH:mm')}
                        </span>
                      </div>
                    </div>
                  </div>
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => handleStopTransaction(tx.connectorId)}
                    disabled={stopTx.isPending}
                  >
                    <Square className="h-3.5 w-3.5 mr-1" />
                    Stop
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <div className="space-y-3">
        <h3 className="text-sm font-medium text-muted-foreground">Transaction History</h3>
        <div className="bg-card border border-border rounded-lg overflow-hidden">
          <table className="w-full">
            <thead className="bg-secondary/50">
              <tr className="text-left text-xs text-muted-foreground">
                <th className="px-4 py-3 font-medium">Transaction ID</th>
                <th className="px-4 py-3 font-medium">Connector</th>
                <th className="px-4 py-3 font-medium">ID Tag</th>
                <th className="px-4 py-3 font-medium">Start Time</th>
                <th className="px-4 py-3 font-medium">End Time</th>
                <th className="px-4 py-3 font-medium">Energy (Wh)</th>
                <th className="px-4 py-3 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              <tr className="text-sm text-muted-foreground">
                <td colSpan={7} className="px-4 py-6 text-center">
                  No completed transactions yet
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
