import { useState } from 'react';
import { useChargerLogs, useClearChargerLogs } from '@/api/chargers';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Search, Trash2, ArrowDownLeft, ArrowUpRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { format } from 'date-fns';

const LOGS_POLL_INTERVAL_MS = 2000;

interface LogsTabProps {
  chargePointId: string | undefined;
}

export function LogsTab({ chargePointId }: LogsTabProps) {
  const [filter, setFilter] = useState('');
  const { data: logs = [], isLoading } = useChargerLogs(chargePointId, LOGS_POLL_INTERVAL_MS);
  const clearLogs = useClearChargerLogs(chargePointId);

  const filteredLogs = logs
    .filter(
      (log) =>
        log.messageType.toLowerCase().includes(filter.toLowerCase()) ||
        log.payload.toLowerCase().includes(filter.toLowerCase())
    )
    .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Filter logs..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="pl-9 bg-secondary border-border"
          />
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => clearLogs.mutate()}
          disabled={!chargePointId || clearLogs.isPending || logs.length === 0}
        >
          <Trash2 className="h-4 w-4 mr-1" />
          Clear
        </Button>
      </div>

      <div className="bg-card border border-border rounded-lg overflow-hidden">
        <div className="max-h-[500px] overflow-y-auto">
          {isLoading ? (
            <p className="p-4 text-sm text-muted-foreground">Loading logs…</p>
          ) : filteredLogs.length === 0 ? (
            <p className="p-4 text-sm text-muted-foreground">
              {logs.length === 0 ? 'No OCPP messages yet for this session. Connect to a CSMS to see traffic.' : 'No logs match the filter.'}
            </p>
          ) : (
            filteredLogs.map((log) => (
              <div
                key={log.id}
                className={cn(
                  'log-entry flex items-start gap-3 border-b border-border last:border-0 hover:bg-secondary/50 transition-colors',
                  log.direction === 'incoming' ? 'log-entry-request' : 'log-entry-response',
                  log.status === 'error' && 'log-entry-error'
                )}
              >
                <div className="flex items-center gap-2 min-w-[180px] py-2">
                  {log.direction === 'incoming' ? (
                    <ArrowDownLeft className="h-3.5 w-3.5 text-success shrink-0" />
                  ) : (
                    <ArrowUpRight className="h-3.5 w-3.5 text-warning shrink-0" />
                  )}
                  <span className="text-xs text-muted-foreground">
                    {format(new Date(log.timestamp), 'HH:mm:ss.SSS')}
                  </span>
                </div>
                <div className="flex-1 py-2 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <Badge variant="secondary" className="font-mono text-xs">
                      {log.messageType}
                    </Badge>
                    {log.status === 'error' && (
                      <Badge variant="destructive" className="text-xs">
                        Error
                      </Badge>
                    )}
                  </div>
                  <pre className="text-xs text-muted-foreground overflow-x-auto whitespace-pre-wrap break-all">
                    {log.payload}
                  </pre>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      <p className="text-xs text-muted-foreground text-center">
        Showing {filteredLogs.length} of {logs.length} log entries
      </p>
    </div>
  );
}
