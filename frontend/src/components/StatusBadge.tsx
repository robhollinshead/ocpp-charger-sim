import { ChargerStatus } from '@/types/ocpp';
import { cn } from '@/lib/utils';

interface StatusBadgeProps {
  status: ChargerStatus;
  size?: 'sm' | 'md';
}

const statusConfig: Record<ChargerStatus, { class: string; dot: string }> = {
  Available: { class: 'status-available', dot: 'bg-success' },
  Charging: { class: 'status-charging', dot: 'bg-warning animate-pulse-glow' },
  Preparing: { class: 'status-preparing', dot: 'bg-accent' },
  Offline: { class: 'status-offline', dot: 'bg-destructive' },
  Faulted: { class: 'status-offline', dot: 'bg-destructive' },
};

export function StatusBadge({ status, size = 'md' }: StatusBadgeProps) {
  const config = statusConfig[status];
  
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border font-medium',
        config.class,
        size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-3 py-1 text-sm'
      )}
    >
      <span className={cn('rounded-full', config.dot, size === 'sm' ? 'h-1.5 w-1.5' : 'h-2 w-2')} />
      {status}
    </span>
  );
}
