import { useState } from 'react';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ChevronDown, ChevronUp, Zap } from 'lucide-react';
import { toast } from 'sonner';
import { useInjectStatus } from '@/api/chargers';
import type { ChargerDetailResponse } from '@/types/ocpp';

// ---------------------------------------------------------------------------
// Constants (exported for tests)
// ---------------------------------------------------------------------------

/** Valid OCPP 1.6 state transitions per connector. */
export const VALID_TRANSITIONS: Record<string, string[]> = {
  Available:     ['Preparing', 'Unavailable'],
  Preparing:     ['Charging', 'Available', 'Faulted', 'Unavailable'],
  Charging:      ['Finishing', 'SuspendedEV', 'SuspendedEVSE', 'Faulted', 'Unavailable'],
  SuspendedEV:   ['Charging', 'Finishing', 'Faulted', 'Unavailable'],
  SuspendedEVSE: ['Charging', 'Finishing', 'Faulted', 'Unavailable'],
  Finishing:     ['Available', 'Faulted', 'Unavailable'],
  Faulted:       ['Available', 'Unavailable'],
  Unavailable:   ['Available'],
};

/** ChargePointErrorCode values valid for Faulted status. NoError is excluded. */
export const FAULTED_ERROR_CODES: string[] = [
  'ConnectorLockFailure',
  'EVCommunicationError',
  'GroundFailure',
  'HighTemperature',
  'InternalError',
  'LocalListConflict',
  'OtherError',
  'OverCurrentFailure',
  'OverVoltage',
  'PowerMeterFailure',
  'PowerSwitchFailure',
  'ReaderFailure',
  'ResetFailure',
  'UnderVoltage',
  'WeakSignal',
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface InjectStatusPanelProps {
  chargePointId: string;
  charger: ChargerDetailResponse;
}

export function InjectStatusPanel({ chargePointId, charger }: InjectStatusPanelProps) {
  const [open, setOpen] = useState(true);
  const [selectedEvseId, setSelectedEvseId] = useState<number>(
    charger.evses[0]?.evse_id ?? 1
  );
  const [selectedStatus, setSelectedStatus] = useState('');
  const [errorCode, setErrorCode] = useState('');
  const [info, setInfo] = useState('');
  const [vendorErrorCode, setVendorErrorCode] = useState('');

  const injectStatus = useInjectStatus(chargePointId);

  const selectedEvse = charger.evses.find((e) => e.evse_id === selectedEvseId);
  const currentState = selectedEvse?.state ?? 'Available';
  const validStatuses = VALID_TRANSITIONS[currentState] ?? [];
  const isFaulted = selectedStatus === 'Faulted';

  function resetFaultFields() {
    setErrorCode('');
    setInfo('');
    setVendorErrorCode('');
  }

  function handleEvseChange(value: string) {
    setSelectedEvseId(Number(value));
    setSelectedStatus('');
    resetFaultFields();
  }

  function handleStatusChange(value: string) {
    setSelectedStatus(value);
    resetFaultFields();
  }

  function handleSubmit() {
    if (!selectedStatus) {
      toast.error('Select a status to inject');
      return;
    }
    if (isFaulted && !errorCode) {
      toast.error('Error code is required for Faulted status');
      return;
    }
    injectStatus.mutate(
      {
        connector_id: selectedEvseId,
        status: selectedStatus,
        error_code: isFaulted ? errorCode : undefined,
        info: isFaulted ? info || undefined : undefined,
        vendor_error_code: isFaulted ? vendorErrorCode || undefined : undefined,
      },
      {
        onSuccess: () => toast.success('Status injected successfully'),
      }
    );
  }

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <div className="bg-card border border-border rounded-lg">
        <CollapsibleTrigger asChild>
          <button className="w-full flex items-center justify-between p-3 text-left hover:bg-secondary/50 transition-colors rounded-t-lg">
            <div className="flex items-center gap-2">
              <Zap className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm font-medium">Inject Status</span>
            </div>
            {open ? (
              <ChevronUp className="h-4 w-4 text-muted-foreground" />
            ) : (
              <ChevronDown className="h-4 w-4 text-muted-foreground" />
            )}
          </button>
        </CollapsibleTrigger>

        <CollapsibleContent>
          <div className="px-3 pb-3 space-y-3 border-t border-border pt-3">
            <div className="grid grid-cols-2 gap-3">
              {/* EVSE selector */}
              <div className="space-y-1.5">
                <Label htmlFor="inject-evse-select">EVSE</Label>
                <Select value={String(selectedEvseId)} onValueChange={handleEvseChange}>
                  <SelectTrigger id="inject-evse-select" className="bg-secondary border-border">
                    <SelectValue placeholder="Select EVSE" />
                  </SelectTrigger>
                  <SelectContent>
                    {charger.evses.map((evse) => (
                      <SelectItem key={evse.evse_id} value={String(evse.evse_id)}>
                        EVSE {evse.evse_id} — {evse.state}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Status selector — filtered by valid transitions from current EVSE state */}
              <div className="space-y-1.5">
                <Label htmlFor="inject-status-select">New Status</Label>
                <Select value={selectedStatus} onValueChange={handleStatusChange}>
                  <SelectTrigger id="inject-status-select" className="bg-secondary border-border">
                    <SelectValue placeholder="Select status" />
                  </SelectTrigger>
                  <SelectContent>
                    {validStatuses.map((s) => (
                      <SelectItem key={s} value={s}>
                        {s}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Faulted-specific fields */}
            {isFaulted && (
              <div className="grid grid-cols-3 gap-3 p-3 bg-secondary/40 rounded-md border border-border">
                <div className="space-y-1.5">
                  <Label htmlFor="inject-error-code-select">
                    Error Code <span className="text-destructive">*</span>
                  </Label>
                  <Select value={errorCode} onValueChange={setErrorCode}>
                    <SelectTrigger id="inject-error-code-select" className="bg-background border-border">
                      <SelectValue placeholder="Select error code" />
                    </SelectTrigger>
                    <SelectContent>
                      {FAULTED_ERROR_CODES.map((ec) => (
                        <SelectItem key={ec} value={ec}>
                          {ec}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="inject-info-input">Info</Label>
                  <Input
                    id="inject-info-input"
                    placeholder="Diagnostic info..."
                    value={info}
                    onChange={(e) => setInfo(e.target.value)}
                    className="bg-background border-border"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="inject-vendor-error-input">Vendor Error Code</Label>
                  <Input
                    id="inject-vendor-error-input"
                    placeholder="e.g. E42"
                    value={vendorErrorCode}
                    onChange={(e) => setVendorErrorCode(e.target.value)}
                    className="bg-background border-border"
                  />
                </div>
              </div>
            )}

            <Button
              size="sm"
              data-testid="inject-status-submit"
              onClick={handleSubmit}
              disabled={!selectedStatus || injectStatus.isPending}
            >
              <Zap className="h-3.5 w-3.5 mr-1.5" />
              {injectStatus.isPending ? 'Injecting…' : 'Inject Status'}
            </Button>
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
}
