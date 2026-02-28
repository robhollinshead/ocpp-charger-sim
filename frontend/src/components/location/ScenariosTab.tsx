import { useState } from 'react';
import { toast } from 'sonner';
import { Play, Square, StopCircle, AlertTriangle, WifiOff } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Progress } from '@/components/ui/progress';
import {
  useActiveScenario,
  useStartRushPeriod,
  useStopScenario,
  useStopAllCharging,
} from '@/api/scenarios';

interface ScenariosTabProps {
  locationId: string | undefined;
}

function StatusBadge({ status }: { status: string }) {
  if (status === 'running') {
    return <Badge className="bg-blue-500/20 text-blue-400 border-blue-500/30">Running</Badge>;
  }
  if (status === 'completed') {
    return <Badge className="bg-green-500/20 text-green-400 border-green-500/30">Completed</Badge>;
  }
  return <Badge variant="secondary">Cancelled</Badge>;
}

export function ScenariosTab({ locationId }: ScenariosTabProps) {
  const [durationMinutes, setDurationMinutes] = useState(5);

  // Poll every 2 s — the endpoint is lightweight and keeps progress up to date
  const { data: activeScenario, isLoading: scenarioLoading } = useActiveScenario(locationId, 2000);

  const startRushPeriod = useStartRushPeriod(locationId);
  const stopScenario = useStopScenario(locationId);
  const stopAllCharging = useStopAllCharging(locationId);

  const scenarioIsRunning = activeScenario?.status === 'running';

  async function handleStartRushPeriod() {
    try {
      await startRushPeriod.mutateAsync(durationMinutes);
      toast.success('Rush Period scenario started');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to start scenario');
    }
  }

  async function handleStopScenario() {
    try {
      await stopScenario.mutateAsync();
      toast.success('Scenario stopped — no further plug-ins will occur');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to stop scenario');
    }
  }

  async function handleStopAllCharging() {
    try {
      const result = await stopAllCharging.mutateAsync();
      if (result.stopped === 0) {
        toast.info('No active charging sessions found');
      } else {
        const msg =
          result.errors > 0
            ? `Stopped ${result.stopped} session${result.stopped !== 1 ? 's' : ''} (${result.errors} error${result.errors !== 1 ? 's' : ''})`
            : `Stopped ${result.stopped} charging session${result.stopped !== 1 ? 's' : ''}`;
        toast.success(msg);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to stop charging sessions');
    }
  }

  const progressPct =
    activeScenario && activeScenario.total_pairs > 0
      ? Math.round((activeScenario.completed_pairs / activeScenario.total_pairs) * 100)
      : 0;

  return (
    <div className="space-y-6">
      {/* Stop All Charging — always visible */}
      <Card className="bg-card border-border">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Emergency Stop</CardTitle>
          <CardDescription>
            Send StopTransaction to every currently charging EVSE at this location.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button
            variant="destructive"
            onClick={handleStopAllCharging}
            disabled={stopAllCharging.isPending}
          >
            <StopCircle className="h-4 w-4 mr-2" />
            {stopAllCharging.isPending ? 'Stopping…' : 'Stop All Charging'}
          </Button>
        </CardContent>
      </Card>

      {/* Rush Period scenario */}
      <Card className="bg-card border-border">
        <CardHeader>
          <div className="flex items-start justify-between">
            <div>
              <CardTitle>Rush Period</CardTitle>
              <CardDescription className="mt-1.5">
                Simulate a wave of EVs arriving and plugging in over a defined time window. The
                engine connects any offline chargers, then spreads plug-ins evenly across all
                available connectors and vehicles.
              </CardDescription>
            </div>
            {activeScenario && <StatusBadge status={activeScenario.status} />}
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Config */}
          <div className="flex items-end gap-4">
            <div className="space-y-1.5 w-40">
              <Label htmlFor="duration">Duration (minutes)</Label>
              <Input
                id="duration"
                type="number"
                min={1}
                max={480}
                value={durationMinutes}
                onChange={(e) => setDurationMinutes(Math.max(1, parseInt(e.target.value, 10) || 1))}
                disabled={scenarioIsRunning}
              />
            </div>
            {scenarioIsRunning ? (
              <Button
                variant="outline"
                onClick={handleStopScenario}
                disabled={stopScenario.isPending}
              >
                <Square className="h-4 w-4 mr-2" />
                {stopScenario.isPending ? 'Stopping…' : 'Stop Scenario'}
              </Button>
            ) : (
              <Button
                onClick={handleStartRushPeriod}
                disabled={startRushPeriod.isPending || scenarioLoading}
              >
                <Play className="h-4 w-4 mr-2" />
                {startRushPeriod.isPending ? 'Starting…' : 'Start Rush Period'}
              </Button>
            )}
          </div>

          {/* Status panel */}
          {activeScenario && (
            <div className="rounded-lg border border-border bg-muted/30 p-4 space-y-3">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">
                  {activeScenario.status === 'running'
                    ? `Plugging in over ${activeScenario.duration_minutes} min…`
                    : activeScenario.status === 'completed'
                      ? 'Scenario complete — charging is under way'
                      : 'Scenario cancelled'}
                </span>
                <span className="font-medium tabular-nums">
                  {activeScenario.completed_pairs} / {activeScenario.total_pairs} plugged in
                </span>
              </div>

              {activeScenario.total_pairs > 0 && (
                <Progress value={progressPct} className="h-2" />
              )}

              {activeScenario.failed_pairs > 0 && (
                <div className="flex items-center gap-2 text-sm text-yellow-500">
                  <AlertTriangle className="h-4 w-4 flex-shrink-0" />
                  {activeScenario.failed_pairs} plug-in{activeScenario.failed_pairs !== 1 ? 's' : ''} failed
                </div>
              )}

              {activeScenario.offline_charger_ids.length > 0 && (
                <div className="space-y-1">
                  <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
                    <WifiOff className="h-4 w-4" />
                    Offline chargers (skipped):
                  </div>
                  <ul className="ml-6 text-xs text-muted-foreground list-disc space-y-0.5">
                    {activeScenario.offline_charger_ids.map((id) => (
                      <li key={id}>{id}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
