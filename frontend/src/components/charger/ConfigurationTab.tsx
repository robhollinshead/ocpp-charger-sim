import { useState, useMemo, useEffect } from 'react';
import type { ChargerDetailResponse, ChargerConfigUpdate } from '@/types/ocpp';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Save, RotateCcw, Lock } from 'lucide-react';
import { toast } from 'sonner';
import { useUpdateChargerConfig } from '@/api/chargers';

const EDITABLE_KEYS = [
  { key: 'HeartbeatInterval' as const, type: 'number' as const, label: 'HeartbeatInterval' },
  { key: 'ConnectionTimeOut' as const, type: 'number' as const, label: 'ConnectionTimeOut' },
  { key: 'MeterValuesSampleInterval' as const, type: 'number' as const, label: 'MeterValuesSampleInterval' },
  { key: 'ClockAlignedDataInterval' as const, type: 'number' as const, label: 'ClockAlignedDataInterval' },
  { key: 'AuthorizeRemoteTxRequests' as const, type: 'boolean' as const, label: 'AuthorizeRemoteTxRequests' },
  { key: 'LocalAuthListEnabled' as const, type: 'boolean' as const, label: 'LocalAuthListEnabled' },
  { key: 'OCPPAuthorizationEnabled' as const, type: 'boolean' as const, label: 'OCPPAuthorizationEnabled' },
] as const;

interface ConfigurationTabProps {
  charger: ChargerDetailResponse;
}

export function ConfigurationTab({ charger }: ConfigurationTabProps) {
  const updateConfig = useUpdateChargerConfig(charger.charge_point_id);
  const defaults: Record<string, number | boolean> = {
    HeartbeatInterval: 120,
    ConnectionTimeOut: 60,
    MeterValuesSampleInterval: 30,
    ClockAlignedDataInterval: 900,
    AuthorizeRemoteTxRequests: true,
    LocalAuthListEnabled: true,
    OCPPAuthorizationEnabled: true,
  };

  const initialEditable = useMemo(() => {
    const c = charger.config || {};
    return EDITABLE_KEYS.reduce(
      (acc, { key }) => {
        if (c[key] !== undefined) {
          acc[key] = typeof c[key] === 'boolean' ? c[key] : Number(c[key]);
        } else {
          acc[key] = defaults[key];
        }
        return acc;
      },
      {} as Record<string, number | boolean>
    );
  }, [charger.charge_point_id, charger.config]);

  const [editable, setEditable] = useState<Record<string, number | boolean>>(initialEditable);
  const [hasChanges, setHasChanges] = useState(false);

  useEffect(() => {
    setEditable(initialEditable);
    setHasChanges(false);
  }, [charger.charge_point_id, initialEditable]);

  const handleEditableChange = (key: string, value: number | boolean) => {
    setEditable((prev) => ({ ...prev, [key]: value }));
    setHasChanges(true);
  };

  const handleSave = async () => {
    const payload: ChargerConfigUpdate = {};
    EDITABLE_KEYS.forEach(({ key }) => {
      if (editable[key] !== undefined) payload[key] = editable[key];
    });
    try {
      await updateConfig.mutateAsync(payload);
      toast.success('Configuration saved successfully');
      setHasChanges(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to save configuration');
    }
  };

  const handleReset = () => {
    setEditable(initialEditable);
    setHasChanges(false);
    toast.info('Configuration reset to saved values');
  };

  const readOnlyRows = [
    { key: 'ChargePointId', value: charger.charge_point_id },
    { key: 'ChargePointVendor', value: charger.charge_point_vendor ?? 'FastCharge' },
    { key: 'ChargePointModel', value: charger.charge_point_model ?? 'Pro 150' },
    { key: 'FirmwareVersion', value: charger.firmware_version ?? '2.4.1' },
  ];

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
          <Button size="sm" onClick={handleSave} disabled={!hasChanges || updateConfig.isPending}>
            <Save className="h-4 w-4 mr-1" />
            {updateConfig.isPending ? 'Saving…' : 'Save Changes'}
          </Button>
        </div>
      </div>

      <div className="grid gap-4">
        <Card className="bg-card border-border">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-muted-foreground">Read-Only Properties</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {readOnlyRows.map((row) => (
              <div key={row.key} className="flex items-center justify-between py-2 px-3 bg-secondary/50 rounded-lg">
                <div className="flex items-center gap-2">
                  <Lock className="h-3.5 w-3.5 text-muted-foreground" />
                  <span className="font-mono text-sm">{row.key}</span>
                </div>
                <span className="font-mono text-sm text-foreground">{row.value}</span>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card className="bg-card border-border">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-muted-foreground">Configurable Settings</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {EDITABLE_KEYS.map(({ key, type, label }) => (
              <div key={key} className="flex items-center justify-between py-2">
                <label className="font-mono text-sm">{label}</label>
                {type === 'boolean' ? (
                  <Switch
                    checked={editable[key] === true}
                    onCheckedChange={(checked) => handleEditableChange(key, checked)}
                  />
                ) : (
                  <Input
                    type="number"
                    value={editable[key] as number}
                    onChange={(e) => {
                      const v = e.target.value === '' ? 0 : parseInt(e.target.value, 10);
                      handleEditableChange(key, isNaN(v) ? 0 : v);
                    }}
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
