import type { WatcherEvent } from '../types/watchers';

export interface MetricPoint {
  name: string;
  value: number;
  timestamp: string;
  jobId: string;
  watcherName: string;
}

export interface MetricSummary {
  latest: number;
  avg: number;
  min: number;
  max: number;
  count: number;
  trend: 'up' | 'down' | 'stable';
  deltaPercent: number;
}

export interface MetricSeries {
  name: string;
  points: MetricPoint[];
  summary: MetricSummary;
}

export const METRIC_COLORS = [
  '#2563eb',
  '#059669',
  '#d97706',
  '#dc2626',
  '#7c3aed',
  '#0891b2',
];

export function extractMetricPoints(events: WatcherEvent[]): MetricPoint[] {
  return events
    .filter((event) => event.action_type === 'store_metric' && event.captured_vars)
    .map((event) => ({
      name: String(event.captured_vars.name || event.captured_vars.metric_name || 'unknown'),
      value: parseFloat(String(event.captured_vars.value || event.captured_vars.metric_value || '0')),
      timestamp: event.timestamp,
      jobId: event.job_id,
      watcherName: event.watcher_name,
    }))
    .filter((point) => Number.isFinite(point.value))
    .sort(
      (left, right) =>
        new Date(left.timestamp).getTime() - new Date(right.timestamp).getTime(),
    );
}

export function summarizeMetricPoints(points: MetricPoint[]): MetricSummary | null {
  if (points.length === 0) return null;

  const values = points.map((point) => point.value);
  const latest = points.at(-1)?.value ?? 0;
  const avg = values.reduce((sum, value) => sum + value, 0) / values.length;
  const min = Math.min(...values);
  const max = Math.max(...values);

  const recentWindow = points.slice(-Math.min(points.length, 10));
  const firstValue = recentWindow[0]?.value ?? latest;
  const lastValue = recentWindow.at(-1)?.value ?? latest;
  const rawDelta = lastValue - firstValue;
  const deltaPercent =
    Math.abs(firstValue) < 1e-9
      ? rawDelta === 0
        ? 0
        : rawDelta > 0
          ? 100
          : -100
      : (rawDelta / firstValue) * 100;

  let trend: MetricSummary['trend'] = 'stable';
  if (deltaPercent > 5) trend = 'up';
  else if (deltaPercent < -5) trend = 'down';

  return {
    latest,
    avg,
    min,
    max,
    count: points.length,
    trend,
    deltaPercent,
  };
}

export function buildMetricSeries(events: WatcherEvent[]): MetricSeries[] {
  const grouped = new Map<string, MetricPoint[]>();

  extractMetricPoints(events).forEach((point) => {
    const existing = grouped.get(point.name) ?? [];
    existing.push(point);
    grouped.set(point.name, existing);
  });

  return Array.from(grouped.entries())
    .map(([name, points]) => ({
      name,
      points,
      summary: summarizeMetricPoints(points)!,
    }))
    .sort((left, right) => {
      const leftTime = new Date(left.points.at(-1)?.timestamp ?? 0).getTime();
      const rightTime = new Date(right.points.at(-1)?.timestamp ?? 0).getTime();
      return rightTime - leftTime;
    });
}

export function getDefaultSelectedMetricNames(
  metricNames: string[],
  maxSelections = 2,
): string[] {
  return metricNames.slice(0, maxSelections);
}
