import { describe, expect, it } from 'vitest';

import type { WatcherEvent } from '../types/watchers';
import {
  buildMetricSeries,
  extractMetricPoints,
  getDefaultSelectedMetricNames,
  summarizeMetricPoints,
} from './watcherMetrics';

function buildEvent(overrides: Partial<WatcherEvent>): WatcherEvent {
  return {
    id: 1,
    watcher_id: 7,
    watcher_name: 'Loss tracker',
    job_id: '90210',
    hostname: 'cluster-alpha.internal',
    timestamp: '2026-03-21T09:00:00.000Z',
    matched_text: 'loss=1.0',
    captured_vars: { name: 'loss', value: '1.0' },
    action_type: 'store_metric',
    action_result: 'stored',
    success: true,
    ...overrides,
  };
}

describe('watcherMetrics helpers', () => {
  it('extracts only numeric metric points in chronological order', () => {
    const points = extractMetricPoints([
      buildEvent({
        timestamp: '2026-03-21T09:02:00.000Z',
        captured_vars: { name: 'loss', value: '0.8' },
      }),
      buildEvent({
        id: 2,
        timestamp: '2026-03-21T09:01:00.000Z',
        captured_vars: { name: 'loss', value: '0.9' },
      }),
      buildEvent({
        id: 3,
        action_type: 'log',
        captured_vars: { message: 'not a metric' },
      }),
      buildEvent({
        id: 4,
        captured_vars: { name: 'loss', value: 'nan' },
      }),
    ]);

    expect(points).toHaveLength(2);
    expect(points.map((point) => point.value)).toEqual([0.9, 0.8]);
  });

  it('summarizes metric trends and delta percentages', () => {
    const summary = summarizeMetricPoints([
      {
        name: 'accuracy',
        value: 0.5,
        timestamp: '2026-03-21T09:00:00.000Z',
        jobId: '90210',
        watcherName: 'Validation accuracy observer',
      },
      {
        name: 'accuracy',
        value: 0.65,
        timestamp: '2026-03-21T09:05:00.000Z',
        jobId: '90210',
        watcherName: 'Validation accuracy observer',
      },
      {
        name: 'accuracy',
        value: 0.8,
        timestamp: '2026-03-21T09:10:00.000Z',
        jobId: '90210',
        watcherName: 'Validation accuracy observer',
      },
    ]);

    expect(summary).not.toBeNull();
    expect(summary?.latest).toBeCloseTo(0.8);
    expect(summary?.trend).toBe('up');
    expect(summary?.deltaPercent).toBeCloseTo(60);
  });

  it('builds named series and picks stable default selections', () => {
    const series = buildMetricSeries([
      buildEvent({ captured_vars: { name: 'loss', value: '0.8' } }),
      buildEvent({
        id: 2,
        timestamp: '2026-03-21T09:10:00.000Z',
        captured_vars: { name: 'gpu_mem', value: '72' },
      }),
      buildEvent({
        id: 3,
        timestamp: '2026-03-21T09:12:00.000Z',
        captured_vars: { name: 'val_acc', value: '0.88' },
      }),
    ]);

    expect(series.map((entry) => entry.name)).toEqual(['val_acc', 'gpu_mem', 'loss']);
    expect(getDefaultSelectedMetricNames(series.map((entry) => entry.name))).toEqual([
      'val_acc',
      'gpu_mem',
    ]);
  });
});
