import { cn } from '@/lib/utils';

/** Maps backend EVSE state strings to chip style (same as StatusBadge where applicable). */
const OCPP_STATUS_STYLES: Record<string, { class: string; dot: string }> = {
  Available: { class: 'status-available', dot: 'bg-success' },
  Charging: { class: 'status-charging', dot: 'bg-warning animate-pulse-glow' },
  Preparing: { class: 'status-preparing', dot: 'bg-accent' },
  Finishing: { class: 'status-preparing', dot: 'bg-accent' },
  Faulted: { class: 'status-offline', dot: 'bg-destructive' },
  SuspendedEV: { class: 'status-preparing', dot: 'bg-accent' },
  SuspendedEVSE: { class: 'status-preparing', dot: 'bg-accent' },
  Unavailable: { class: 'status-offline', dot: 'bg-destructive' },
};

interface OcppStatusChipProps {
  status: string | null | undefined;
  size?: 'sm' | 'md';
}

export function OcppStatusChip({ status, size = 'md' }: OcppStatusChipProps) {
  const isNa = status == null || status === '';
  const config = !isNa ? OCPP_STATUS_STYLES[status] ?? { class: 'bg-muted/50 text-muted-foreground border-border', dot: 'bg-muted-foreground' } : null;

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border font-medium font-mono',
        size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-3 py-1 text-sm',
        isNa
          ? 'bg-muted/30 text-muted-foreground border-border opacity-80'
          : config!.class
      )}
    >
      {!isNa && (
        <span
          className={cn(
            'rounded-full shrink-0',
            config!.dot,
            size === 'sm' ? 'h-1.5 w-1.5' : 'h-2 w-2'
          )}
        />
      )}
      {isNa ? 'N/A' : status}
    </span>
  );
}
