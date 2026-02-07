import { useState } from 'react';
import { chargingScenarios } from '@/data/mockData';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { Play, Square, Clock, Car, Zap, Activity } from 'lucide-react';
import { toast } from 'sonner';

interface RunningScenario {
  id: string;
  progress: number;
  vehiclesActive: number;
}

export function ScenariosTab() {
  const [runningScenarios, setRunningScenarios] = useState<RunningScenario[]>([]);

  const handleStartScenario = (scenarioId: string) => {
    const scenario = chargingScenarios.find(s => s.id === scenarioId);
    if (!scenario) return;

    setRunningScenarios([...runningScenarios, { id: scenarioId, progress: 0, vehiclesActive: 0 }]);
    toast.success(`Started scenario: ${scenario.name}`);

    // Simulate progress
    const interval = setInterval(() => {
      setRunningScenarios(prev => {
        const updated = prev.map(rs => {
          if (rs.id === scenarioId) {
            const newProgress = Math.min(rs.progress + Math.random() * 5, 100);
            const newVehicles = Math.floor((newProgress / 100) * scenario.vehicleCount);
            return { ...rs, progress: newProgress, vehiclesActive: newVehicles };
          }
          return rs;
        });

        const current = updated.find(rs => rs.id === scenarioId);
        if (current && current.progress >= 100) {
          clearInterval(interval);
          toast.success(`Scenario "${scenario.name}" completed`);
          return updated.filter(rs => rs.id !== scenarioId);
        }
        return updated;
      });
    }, 500);
  };

  const handleStopScenario = (scenarioId: string) => {
    setRunningScenarios(runningScenarios.filter(rs => rs.id !== scenarioId));
    toast.info('Scenario stopped');
  };

  const isRunning = (id: string) => runningScenarios.some(rs => rs.id === id);
  const getRunningData = (id: string) => runningScenarios.find(rs => rs.id === id);

  const patternColors = {
    sequential: 'bg-accent/20 text-accent border-accent/30',
    random: 'bg-success/20 text-success border-success/30',
    burst: 'bg-warning/20 text-warning border-warning/30',
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold mb-1">Charging Scenarios</h3>
        <p className="text-sm text-muted-foreground">
          Simulate various charging patterns to test charger behavior under different conditions
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {chargingScenarios.map(scenario => {
          const running = isRunning(scenario.id);
          const runningData = getRunningData(scenario.id);

          return (
            <Card
              key={scenario.id}
              className={`bg-card border-border transition-all ${running ? 'ring-1 ring-primary' : ''}`}
            >
              <CardContent className="p-5">
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <h4 className="font-semibold text-foreground">{scenario.name}</h4>
                    <p className="text-sm text-muted-foreground mt-1">{scenario.description}</p>
                  </div>
                  <Badge className={patternColors[scenario.pattern]} variant="outline">
                    {scenario.pattern}
                  </Badge>
                </div>

                <div className="flex items-center gap-4 text-sm text-muted-foreground mb-4">
                  <span className="flex items-center gap-1.5">
                    <Car className="h-4 w-4" />
                    {scenario.vehicleCount} vehicles
                  </span>
                  <span className="flex items-center gap-1.5">
                    <Clock className="h-4 w-4" />
                    {scenario.duration}
                  </span>
                </div>

                {running && runningData && (
                  <div className="space-y-2 mb-4 p-3 bg-secondary/50 rounded-lg">
                    <div className="flex items-center justify-between text-sm">
                      <span className="flex items-center gap-1.5 text-primary">
                        <Activity className="h-4 w-4 animate-pulse" />
                        Running
                      </span>
                      <span className="font-mono">{Math.round(runningData.progress)}%</span>
                    </div>
                    <Progress value={runningData.progress} className="h-2" />
                    <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                      <Zap className="h-3 w-3" />
                      {runningData.vehiclesActive} / {scenario.vehicleCount} vehicles active
                    </div>
                  </div>
                )}

                {running ? (
                  <Button
                    variant="destructive"
                    className="w-full"
                    onClick={() => handleStopScenario(scenario.id)}
                  >
                    <Square className="h-4 w-4 mr-1" />
                    Stop Scenario
                  </Button>
                ) : (
                  <Button
                    variant="outline"
                    className="w-full hover:bg-primary hover:text-primary-foreground"
                    onClick={() => handleStartScenario(scenario.id)}
                  >
                    <Play className="h-4 w-4 mr-1" />
                    Start Scenario
                  </Button>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
