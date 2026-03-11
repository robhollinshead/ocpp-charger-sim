import { useState, useMemo, useEffect } from 'react';
import type { ChargerDetailResponse, ChargerConfigUpdate } from '@/types/ocpp';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Save, RotateCcw, Lock } from 'lucide-react';
import { toast } from 'sonner';
import { useUpdateChargerConfig } from '@/api/chargers';
import { PowerTypeChip } from '@/components/PowerTypeChip';

type EditableKeyType = 'number' | 'boolean' | 'string';

interface EditableKeyDef {
  key: keyof ChargerConfigUpdate;
  type: EditableKeyType;
  label: string;
}

const EDITABLE_KEYS: EditableKeyDef[] = [
  { key: 'HeartbeatInterval', type: 'number', label: 'HeartbeatInterval' },
  { key: 'ConnectionTimeOut', type: 'number', label: 'ConnectionTimeOut' },
  { key: 'MeterValuesSampleInterval', type: 'number', label: 'MeterValuesSampleInterval' },
  { key: 'ClockAlignedDataInterval', type: 'number', label: 'ClockAlignedDataInterval' },
  { key: 'MeterValuesSampledData', type: 'string', label: 'MeterValuesSampledData' },
  { key: 'AuthorizeRemoteTxRequests', type: 'boolean', label: 'AuthorizeRemoteTxRequests' },
  { key: 'LocalAuthListEnabled', type: 'boolean', label: 'LocalAuthListEnabled' },
  { key: 'OCPPAuthorizationEnabled', type: 'boolean', label: 'OCPPAuthorizationEnabled' },
  { key: 'TxDefaultPowerW', type: 'number', label: 'TxDefaultPowerW' },
];

const DEFAULT_MEASURANDS_DC = 'Energy.Active.Import.Register,Power.Active.Import,Current.Import,SoC';
const DEFAULT_MEASURANDS_AC = 'Energy.Active.Import.Register,Power.Active.Import,Current.Import';

const STATIC_DEFAULTS: Record<string, number | boolean> = {
  HeartbeatInterval: 120,
  ConnectionTimeOut: 60,
  MeterValuesSampleInterval: 30,
  ClockAlignedDataInterval: 900,
  AuthorizeRemoteTxRequests: true,
  LocalAuthListEnabled: true,
  OCPPAuthorizationEnabled: true,
};

interface ConfigurationTabProps {
  charger: ChargerDetailResponse;
}

export function ConfigurationTab({ charger }: ConfigurationTabProps) {
  const updateConfig = useUpdateChargerConfig(charger.charge_point_id);

  const initialEditable = useMemo(() => {
    const c = charger.config || {};
    const measurandDefault = charger.power_type === 'AC' ? DEFAULT_MEASURANDS_AC : DEFAULT_MEASURANDS_DC;
    return EDITABLE_KEYS.reduce(
      (acc, { key, type }) => {
        if (c[key] !== undefined) {
          if (type === 'boolean') {
            acc[key] = Boolean(c[key]);
          } else if (type === 'number') {
            acc[key] = Number(c[key]);
          } else {
            acc[key] = String(c[key]);
          }
        } else if (key === 'MeterValuesSampledData') {
          acc[key] = measurandDefault;
        } else {
          acc[key] = STATIC_DEFAULTS[key] ?? '';
        }
        return acc;
      },
      {} as Record<string, number | boolean | string>
    );
  }, [charger.charge_point_id, charger.config, charger.power_type]);

  const [editable, setEditable] = useState<Record<string, number | boolean | string>>(initialEditable);
  const [hasChanges, setHasChanges] = useState(false);

  useEffect(() => {
    setEditable(initialEditable);
    setHasChanges(false);
  }, [charger.charge_point_id, initialEditable]);

  const handleEditableChange = (key: string, value: number | boolean | string) => {
    setEditable((prev) => ({ ...prev, [key]: value }));
    setHasChanges(true);
  };

  const handleSave = async () => {
    const payload: ChargerConfigUpdate = {};
    EDITABLE_KEYS.forEach(({ key, type }) => {
      const val = editable[key];
      if (val !== undefined) {
        if (type === 'string') {
          (payload as Record<string, unknown>)[key] = String(val);
        } else {
          (payload as Record<string, unknown>)[key] = val;
        }
      }
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
    { key: 'PowerType', value: charger.power_type ?? 'DC' },
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
                {row.key === 'PowerType' ? (
                  <PowerTypeChip powerType={row.value === 'AC' ? 'AC' : 'DC'} size="sm" />
                ) : (
                  <span className="font-mono text-sm text-foreground">{row.value}</span>
                )}
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
              <div key={key} className={`flex ${type === 'string' ? 'flex-col gap-1' : 'items-center justify-between'} py-2`}>
                <label className="font-mono text-sm">{label}</label>
                {type === 'boolean' ? (
                  <Switch
                    checked={editable[key] === true}
                    onCheckedChange={(checked) => handleEditableChange(key, checked)}
                  />
                ) : type === 'string' ? (
                  <Input
                    type="text"
                    value={editable[key] as string}
                    onChange={(e) => handleEditableChange(key, e.target.value)}
                    className="w-full h-8 font-mono text-xs bg-secondary border-border"
                    placeholder="Comma-separated measurands"
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
