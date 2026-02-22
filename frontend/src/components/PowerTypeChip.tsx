import { cn } from '@/lib/utils';

interface PowerTypeChipProps {
  powerType: 'AC' | 'DC';
  size?: 'sm' | 'md';
  className?: string;
}

const styles = {
  AC: 'bg-orange-500/20 text-orange-700 dark:text-orange-300 border-orange-500/40',
  DC: 'bg-blue-500/20 text-blue-700 dark:text-blue-300 border-blue-500/40',
} as const;

export function PowerTypeChip({ powerType, size = 'sm', className }: PowerTypeChipProps) {
  const type = powerType === 'AC' ? 'AC' : 'DC';
  return (
    <span
      className={cn(
        'inline-flex font-mono rounded border font-medium',
        styles[type],
        size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-3 py-1 text-sm',
        className
      )}
    >
      {type}
    </span>
  );
}
