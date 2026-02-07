import { useState } from 'react';
import { chargerConfigs } from '@/data/mockData';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Save, RotateCcw, Lock } from 'lucide-react';
import { toast } from 'sonner';

export function ConfigurationTab() {
  const [configs, setConfigs] = useState(chargerConfigs);
  const [hasChanges, setHasChanges] = useState(false);

  const handleValueChange = (key: string, value: string) => {
    setConfigs(configs.map(c => c.key === key ? { ...c, value } : c));
    setHasChanges(true);
  };

  const handleSave = () => {
    toast.success('Configuration saved successfully');
    setHasChanges(false);
  };

  const handleReset = () => {
    setConfigs(chargerConfigs);
    setHasChanges(false);
    toast.info('Configuration reset to original values');
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold">Charger Configuration</h3>
          <p className="text-sm text-muted-foreground">View and modify OCPP configuration keys</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={handleReset} disabled={!hasChanges}>
            <RotateCcw className="h-4 w-4 mr-1" />
            Reset
          </Button>
          <Button size="sm" onClick={handleSave} disabled={!hasChanges}>
            <Save className="h-4 w-4 mr-1" />
            Save Changes
          </Button>
        </div>
      </div>

      <div className="grid gap-4">
        <Card className="bg-card border-border">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-muted-foreground">Read-Only Properties</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {configs.filter(c => c.readonly).map(config => (
              <div key={config.key} className="flex items-center justify-between py-2 px-3 bg-secondary/50 rounded-lg">
                <div className="flex items-center gap-2">
                  <Lock className="h-3.5 w-3.5 text-muted-foreground" />
                  <span className="font-mono text-sm">{config.key}</span>
                </div>
                <span className="font-mono text-sm text-foreground">{config.value}</span>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card className="bg-card border-border">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-muted-foreground">Configurable Settings</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {configs.filter(c => !c.readonly).map(config => (
              <div key={config.key} className="flex items-center justify-between py-2">
                <label className="font-mono text-sm">{config.key}</label>
                {config.type === 'boolean' ? (
                  <Switch
                    checked={config.value === 'true'}
                    onCheckedChange={(checked) => handleValueChange(config.key, checked.toString())}
                  />
                ) : (
                  <Input
                    type={config.type === 'number' ? 'number' : 'text'}
                    value={config.value}
                    onChange={(e) => handleValueChange(config.key, e.target.value)}
                    className="w-32 h-8 font-mono text-sm bg-secondary border-border"
                  />
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
