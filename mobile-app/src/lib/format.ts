import { colors } from '@/src/theme/colors';

export function formatDateTime(value?: string | null) {
  if (!value) {
    return 'Unavailable';
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return `${date.toLocaleDateString()} ${date.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  })}`;
}

export function formatRelativeTimestamp(value?: string | null) {
  if (!value) {
    return 'never';
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  const deltaSeconds = Math.round((date.getTime() - Date.now()) / 1000);
  const absSeconds = Math.abs(deltaSeconds);

  if (absSeconds < 60) {
    return deltaSeconds >= 0 ? 'in a few seconds' : 'just now';
  }

  const units = [
    ['day', 86_400],
    ['hour', 3_600],
    ['minute', 60],
  ] as const;

  for (const [label, divisor] of units) {
    if (absSeconds >= divisor) {
      const amount = Math.round(absSeconds / divisor);
      return deltaSeconds >= 0
        ? `in ${amount} ${label}${amount === 1 ? '' : 's'}`
        : `${amount} ${label}${amount === 1 ? '' : 's'} ago`;
    }
  }

  return value;
}

export function formatBytes(value?: number | null) {
  if (value == null || Number.isNaN(value)) {
    return '0 B';
  }

  const units = ['B', 'KB', 'MB', 'GB'];
  let current = value;
  let unitIndex = 0;
  while (current >= 1024 && unitIndex < units.length - 1) {
    current /= 1024;
    unitIndex += 1;
  }
  return `${current.toFixed(current >= 10 ? 0 : 1)} ${units[unitIndex]}`;
}

export function formatJobMeta(parts: Array<string | null | undefined>) {
  return parts.filter(Boolean).join('  •  ');
}

export function stateColor(state?: string | null) {
  switch (state) {
    case 'R':
    case 'running':
    case 'active':
      return colors.success;
    case 'PD':
    case 'pending':
      return colors.warning;
    case 'CD':
    case 'completed':
      return colors.info;
    case 'F':
    case 'failed':
    case 'CA':
    case 'cancelled':
      return colors.danger;
    case 'paused':
      return colors.warning;
    default:
      return colors.textMuted;
  }
}
