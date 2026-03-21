import { useState } from 'react';
import { BarChart2, ChevronDown, ChevronRight, RefreshCw } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { cn } from '@/lib/utils';
import { useChargingProfiles, useEvaluatedLimit } from '@/api/charging_profiles';
import type { ChargingProfileResponse, EvseStatusResponse } from '@/types/ocpp';

interface ProfilesTabProps {
  chargePointId: string;
  evses: EvseStatusResponse[];
}

function statusVariant(status: string): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (status === 'Active') return 'default';
  if (status === 'Scheduled') return 'secondary';
  return 'outline';
}

function purposeLabel(purpose: string): string {
  if (purpose === 'ChargePointMaxProfile') return 'Max Profile';
  if (purpose === 'TxDefaultProfile') return 'Tx Default';
  if (purpose === 'TxProfile') return 'Tx Profile';
  return purpose;
}

function formatW(w: number | null): string {
  if (w === null) return '—';
  if (w >= 1000) return `${(w / 1000).toFixed(1)} kW`;
  return `${w} W`;
}

function ProfileCard({ profile }: { profile: ChargingProfileResponse }) {
  const [open, setOpen] = useState(false);

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger asChild>
        <button className="w-full text-left">
          <div className="flex items-center justify-between px-4 py-3 hover:bg-secondary/40 rounded-lg transition-colors">
            <div className="flex items-center gap-3 min-w-0">
              {open ? (
                <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" />
              ) : (
                <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
              )}
              <span className="font-mono text-sm font-medium">#{profile.charging_profile_id}</span>
              <Badge variant={statusVariant(profile.status)} className="text-xs">
                {profile.status}
              </Badge>
              <span className="text-sm text-muted-foreground truncate">
                Connector {profile.connector_id === 0 ? 'All' : profile.connector_id}
                {' · '}Stack {profile.stack_level}
                {' · '}{profile.charging_profile_kind}
              </span>
            </div>
            <div className="text-sm font-medium tabular-nums shrink-0 ml-4">
              {profile.status === 'Active' ? formatW(profile.current_limit_W) : '—'}
            </div>
          </div>
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="px-10 pb-4 space-y-3">
          <div className="grid grid-cols-2 gap-2 text-sm">
            {profile.transaction_id !== null && (
              <div>
                <span className="text-muted-foreground">Transaction ID: </span>
                <span className="font-mono">{profile.transaction_id}</span>
              </div>
            )}
            {profile.valid_from && (
              <div>
                <span className="text-muted-foreground">Valid from: </span>
                <span className="font-mono text-xs">{new Date(profile.valid_from).toLocaleString()}</span>
              </div>
            )}
            {profile.valid_to && (
              <div>
                <span className="text-muted-foreground">Valid to: </span>
                <span className="font-mono text-xs">{new Date(profile.valid_to).toLocaleString()}</span>
              </div>
            )}
            {profile.start_schedule && (
              <div>
                <span className="text-muted-foreground">Start: </span>
                <span className="font-mono text-xs">{new Date(profile.start_schedule).toLocaleString()}</span>
              </div>
            )}
            {profile.duration_s !== null && (
              <div>
                <span className="text-muted-foreground">Duration: </span>
                <span>{profile.duration_s}s</span>
              </div>
            )}
            {profile.recurrency_kind && (
              <div>
                <span className="text-muted-foreground">Recurrency: </span>
                <span>{profile.recurrency_kind}</span>
              </div>
            )}
            <div>
              <span className="text-muted-foreground">Received: </span>
              <span className="font-mono text-xs">{new Date(profile.received_at).toLocaleString()}</span>
            </div>
          </div>

          <table className="w-full text-xs border-collapse">
            <thead>
              <tr className="text-muted-foreground border-b border-border">
                <th className="text-left pb-1 font-medium">Start (s)</th>
                <th className="text-right pb-1 font-medium">Limit</th>
                <th className="text-right pb-1 font-medium">Raw</th>
              </tr>
            </thead>
            <tbody>
              {profile.charging_schedule_periods.map((period, i) => (
                <tr
                  key={i}
                  className={cn(
                    'border-b border-border/50',
                    profile.status === 'Active' &&
                      i === profile.charging_schedule_periods.findIndex(
                        (_, idx) =>
                          idx === profile.charging_schedule_periods.length - 1 ||
                          profile.charging_schedule_periods[idx + 1]?.start_period_s > 0
                      )
                      ? 'bg-primary/5'
                      : ''
                  )}
                >
                  <td className="py-1 font-mono">{period.start_period_s}</td>
                  <td className="py-1 text-right font-medium">{formatW(period.limit_W)}</td>
                  <td className="py-1 text-right text-muted-foreground font-mono">
                    {period.raw_limit} {period.raw_unit}
                    {period.number_phases !== null && ` × ${period.number_phases}ph`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

function EvaluatedLimitCard({ chargePointId, connectorId }: { chargePointId: string; connectorId: number }) {
  const { data } = useEvaluatedLimit(chargePointId, connectorId);

  return (
    <div className="flex items-center justify-between py-2 px-3 bg-secondary/30 rounded-md">
      <span className="text-sm text-muted-foreground">Connector {connectorId}</span>
      <div className="text-right">
        {data?.limit_W !== null && data?.limit_W !== undefined ? (
          <span className="text-sm font-semibold text-foreground">{formatW(data.limit_W)}</span>
        ) : (
          <span className="text-sm text-muted-foreground italic">No profile — SuspendedEVSE</span>
        )}
        {data?.capped_by_max_profile && (
          <span className="ml-2 text-xs text-muted-foreground">(capped)</span>
        )}
      </div>
    </div>
  );
}

const PURPOSE_ORDER: ChargingProfileResponse['charging_profile_purpose'][] = [
  'ChargePointMaxProfile',
  'TxDefaultProfile',
  'TxProfile',
];

export function ProfilesTab({ chargePointId, evses }: ProfilesTabProps) {
  const { data: profiles = [], isLoading, refetch } = useChargingProfiles(chargePointId);

  const grouped = PURPOSE_ORDER.reduce(
    (acc, purpose) => {
      acc[purpose] = profiles.filter((p) => p.charging_profile_purpose === purpose);
      return acc;
    },
    {} as Record<string, ChargingProfileResponse[]>,
  );

  return (
    <div className="space-y-6">
      {/* Evaluated limits per EVSE */}
      <Card className="bg-card border-border">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-medium text-muted-foreground uppercase tracking-wide">
              Effective Limits
            </CardTitle>
            <Button variant="ghost" size="sm" onClick={() => refetch()} className="h-7 px-2">
              <RefreshCw className="h-3.5 w-3.5" />
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-2">
          {evses.map((evse) => (
            <EvaluatedLimitCard
              key={evse.evse_id}
              chargePointId={chargePointId}
              connectorId={evse.evse_id}
            />
          ))}
        </CardContent>
      </Card>

      {/* Profiles grouped by purpose */}
      {isLoading ? (
        <p className="text-muted-foreground text-sm">Loading profiles…</p>
      ) : profiles.length === 0 ? (
        <Card className="bg-card border-border">
          <CardContent className="py-10 text-center">
            <BarChart2 className="h-8 w-8 text-muted-foreground mx-auto mb-3" />
            <p className="text-sm text-muted-foreground">
              No charging profiles received from CSMS yet.
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              Without a valid profile, the charger will enter SuspendedEVSE.
            </p>
          </CardContent>
        </Card>
      ) : (
        PURPOSE_ORDER.filter((purpose) => grouped[purpose].length > 0).map((purpose) => (
          <Card key={purpose} className="bg-card border-border">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground uppercase tracking-wide">
                {purposeLabel(purpose)}
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <div className="divide-y divide-border">
                {grouped[purpose].map((profile) => (
                  <ProfileCard key={`${profile.charging_profile_id}-${profile.connector_id}`} profile={profile} />
                ))}
              </div>
            </CardContent>
          </Card>
        ))
      )}
    </div>
  );
}
