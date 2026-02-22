import { cn } from '@/lib/utils';

interface ConnectionBadgeProps {
  connected: boolean;
  size?: 'sm' | 'md';
}

export function ConnectionBadge({ connected, size = 'md' }: ConnectionBadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border font-medium',
        connected
          ? 'bg-success/20 text-success border-success/30'
          : 'bg-muted/50 text-muted-foreground border-border',
        size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-3 py-1 text-sm'
      )}
    >
      <span
        className={cn(
          'rounded-full',
          connected ? 'bg-success' : 'bg-muted-foreground',
          size === 'sm' ? 'h-1.5 w-1.5' : 'h-2 w-2'
        )}
      />
      {connected ? 'Connected' : 'Disconnected'}
    </span>
  );
}
