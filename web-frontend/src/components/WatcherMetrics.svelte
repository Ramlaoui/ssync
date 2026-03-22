<script lang="ts">
  import type { WatcherEvent } from '../types/watchers';
  import {
    METRIC_COLORS,
    buildMetricSeries,
    getDefaultSelectedMetricNames,
  } from '../lib/watcherMetrics';

  interface Props {
    events?: WatcherEvent[];
  }

  interface ChartPoint {
    x: number;
    y: number;
    value: number;
    timestamp: string;
    jobId: string;
    watcherName: string;
  }

  const CHART_WIDTH = 720;
  const CHART_HEIGHT = 320;
  const CHART_PADDING = {
    top: 18,
    right: 24,
    bottom: 42,
    left: 52,
  };
  const MAX_SELECTED_METRICS = 4;
  const MAX_POINTS_PER_SERIES = 24;

  let { events = [] }: Props = $props();

  let selectedMetrics = $state<string[]>([]);

  let metricSeries = $derived(buildMetricSeries(events));
  let metricNames = $derived(metricSeries.map((series) => series.name));

  $effect(() => {
    const validSelection = selectedMetrics.filter((name) => metricNames.includes(name));
    if (validSelection.length === 0 && metricNames.length > 0) {
      selectedMetrics = getDefaultSelectedMetricNames(metricNames);
      return;
    }

    if (validSelection.length !== selectedMetrics.length) {
      selectedMetrics = validSelection;
    }
  });

  let activeSeries = $derived(
    metricSeries
      .filter((series) => selectedMetrics.includes(series.name))
      .map((series, index) => ({
        ...series,
        color: METRIC_COLORS[index % METRIC_COLORS.length],
        visiblePoints: series.points.slice(-MAX_POINTS_PER_SERIES),
      })),
  );

  let compareMode = $derived(activeSeries.length > 1);
  let metricPointCount = $derived(
    activeSeries.reduce((sum, series) => sum + series.visiblePoints.length, 0),
  );

  let allTimestamps = $derived(
    activeSeries.flatMap((series) =>
      series.visiblePoints.map((point) => new Date(point.timestamp).getTime()),
    ),
  );
  let minTimestamp = $derived(allTimestamps.length > 0 ? Math.min(...allTimestamps) : 0);
  let maxTimestamp = $derived(allTimestamps.length > 0 ? Math.max(...allTimestamps) : 1);

  let allVisibleValues = $derived(
    activeSeries.flatMap((series) => series.visiblePoints.map((point) => point.value)),
  );
  let absoluteMin = $derived(allVisibleValues.length > 0 ? Math.min(...allVisibleValues) : 0);
  let absoluteMax = $derived(allVisibleValues.length > 0 ? Math.max(...allVisibleValues) : 1);

  let gridLabels = $derived(
    Array.from({ length: 5 }, (_, index) => {
      const step = index / 4;
      const value = compareMode
        ? 100 - step * 100
        : absoluteMax - (absoluteMax - absoluteMin || 1) * step;
      return {
        value,
        y:
          CHART_PADDING.top +
          ((CHART_HEIGHT - CHART_PADDING.top - CHART_PADDING.bottom) * index) / 4,
      };
    }),
  );

  let chartSeries = $derived(
    activeSeries.map((series) => {
      const seriesMin = Math.min(...series.visiblePoints.map((point) => point.value));
      const seriesMax = Math.max(...series.visiblePoints.map((point) => point.value));
      const seriesRange = seriesMax - seriesMin || 1;
      const timeRange = maxTimestamp - minTimestamp || 1;

      const points: ChartPoint[] = series.visiblePoints.map((point) => {
        const x =
          CHART_PADDING.left +
          ((new Date(point.timestamp).getTime() - minTimestamp) / timeRange) *
            (CHART_WIDTH - CHART_PADDING.left - CHART_PADDING.right);
        const chartValue = compareMode
          ? ((point.value - seriesMin) / seriesRange) * 100
          : point.value;
        const compareMin = compareMode ? 0 : absoluteMin;
        const compareRange = compareMode ? 100 : absoluteMax - absoluteMin || 1;
        const y =
          CHART_PADDING.top +
          (1 - (chartValue - compareMin) / compareRange) *
            (CHART_HEIGHT - CHART_PADDING.top - CHART_PADDING.bottom);

        return {
          x,
          y,
          value: point.value,
          timestamp: point.timestamp,
          jobId: point.jobId,
          watcherName: point.watcherName,
        };
      });

      return {
        ...series,
        points,
        polyline: points.map((point) => `${point.x},${point.y}`).join(' '),
      };
    }),
  );

  let recentRows = $derived(
    chartSeries
      .flatMap((series) =>
        series.visiblePoints.slice(-3).map((point) => ({
          metric: series.name,
          value: point.value,
          timestamp: point.timestamp,
          jobId: point.jobId,
          watcherName: point.watcherName,
          color: series.color,
        })),
      )
      .sort(
        (left, right) =>
          new Date(right.timestamp).getTime() - new Date(left.timestamp).getTime(),
      )
      .slice(0, 8),
  );

  function toggleMetric(name: string) {
    if (selectedMetrics.includes(name)) {
      if (selectedMetrics.length === 1) return;
      selectedMetrics = selectedMetrics.filter((metricName) => metricName !== name);
      return;
    }

    if (selectedMetrics.length >= MAX_SELECTED_METRICS) {
      selectedMetrics = [...selectedMetrics.slice(1), name];
      return;
    }

    selectedMetrics = [...selectedMetrics, name];
  }

  function formatValue(value: number): string {
    if (Math.abs(value) >= 100) return value.toFixed(0);
    if (Math.abs(value) >= 10) return value.toFixed(1);
    return value.toFixed(3);
  }

  function formatAxisValue(value: number): string {
    return compareMode ? `${Math.round(value)}%` : formatValue(value);
  }

  function formatTrend(deltaPercent: number): string {
    if (Math.abs(deltaPercent) < 5) return 'Stable';
    return `${deltaPercent > 0 ? '+' : ''}${deltaPercent.toFixed(1)}%`;
  }
</script>

<div class="metrics-container">
  <div class="metrics-header">
    <div>
      <h3>Metric Comparison</h3>
      <p>
        {#if compareMode}
          Comparing {activeSeries.length} metrics on a normalized scale for shape and trend.
        {:else}
          Track the latest values and trend for the selected metric.
        {/if}
      </p>
    </div>
    {#if metricNames.length > 0}
      <span class="metric-count">{metricPointCount} plotted points</span>
    {/if}
  </div>

  {#if metricNames.length === 0}
    <div class="no-metrics">
      <p>No metrics captured in the current event set.</p>
      <small>Try widening the time filter or clearing the event search.</small>
    </div>
  {:else}
    <div class="metric-selector">
      {#each metricSeries as series, index}
        <button
          class="metric-chip"
          class:active={selectedMetrics.includes(series.name)}
          style="--metric-color: {METRIC_COLORS[index % METRIC_COLORS.length]}"
          onclick={() => toggleMetric(series.name)}
        >
          <span class="metric-dot"></span>
          <span>{series.name}</span>
          <span class="metric-badge">{series.summary.count}</span>
        </button>
      {/each}
    </div>

    <div class="summary-grid">
      {#each chartSeries as series}
        <article class="summary-card" style="--metric-color: {series.color}">
          <div class="summary-header">
            <div class="summary-name">
              <span class="metric-dot"></span>
              <span>{series.name}</span>
            </div>
            <span class="summary-count">{series.summary.count} samples</span>
          </div>
          <div class="summary-value">{formatValue(series.summary.latest)}</div>
          <div class="summary-meta">
            <span>Avg {formatValue(series.summary.avg)}</span>
            <span>Min {formatValue(series.summary.min)}</span>
            <span>Max {formatValue(series.summary.max)}</span>
          </div>
          <div class="summary-trend {series.summary.trend}">
            {formatTrend(series.summary.deltaPercent)}
          </div>
        </article>
      {/each}
    </div>

    <div class="chart-shell">
      <div class="chart-heading">
        <div>
          <h4>{compareMode ? 'Relative Trend Comparison' : 'Metric Trend'}</h4>
          <p>
            {#if compareMode}
              Each line is normalized independently so different units can be compared safely.
            {:else}
              Raw values over time for the selected metric.
            {/if}
          </p>
        </div>
      </div>

      <svg
        class="metric-chart"
        viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
        preserveAspectRatio="none"
        role="img"
        aria-label="Metric comparison chart"
      >
        {#each gridLabels as label}
          <line
            x1={CHART_PADDING.left}
            x2={CHART_WIDTH - CHART_PADDING.right}
            y1={label.y}
            y2={label.y}
            class="grid-line"
          />
          <text x={CHART_PADDING.left - 10} y={label.y + 4} class="axis-label">
            {formatAxisValue(label.value)}
          </text>
        {/each}

        {#each chartSeries as series}
          <polyline
            points={series.polyline}
            fill="none"
            stroke={series.color}
            stroke-width="3"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
          {#each series.points as point, index}
            <circle
              cx={point.x}
              cy={point.y}
              r={index === series.points.length - 1 ? 5 : 3}
              fill={series.color}
              class="chart-point"
            >
              <title>
                {series.name}: {formatValue(point.value)} at {new Date(point.timestamp).toLocaleString()} ({point.watcherName}, job #{point.jobId})
              </title>
            </circle>
          {/each}
        {/each}
      </svg>
    </div>

    <div class="recent-values">
      <div class="recent-header">
        <h4>Latest Values</h4>
        <span>Most recent points across the selected metrics</span>
      </div>
      <div class="values-table">
        {#each recentRows as row}
          <div class="value-row">
            <div class="value-metric">
              <span class="metric-dot" style="background: {row.color}"></span>
              <span>{row.metric}</span>
            </div>
            <span class="value-number">{formatValue(row.value)}</span>
            <span class="value-job">Job #{row.jobId}</span>
            <span class="value-time">{new Date(row.timestamp).toLocaleTimeString()}</span>
          </div>
        {/each}
      </div>
    </div>
  {/if}
</div>

<style>
  .metrics-container {
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    padding: 1.25rem;
    margin-bottom: 1.5rem;
  }

  .metrics-header {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    align-items: flex-start;
    margin-bottom: 1rem;
  }

  .metrics-header h3 {
    margin: 0;
    font-size: 1.1rem;
    color: #111827;
  }

  .metrics-header p {
    margin: 0.35rem 0 0;
    color: #6b7280;
    font-size: 0.9rem;
    max-width: 48rem;
  }

  .metric-count {
    align-self: center;
    background: #eff6ff;
    color: #2563eb;
    border-radius: 999px;
    padding: 0.35rem 0.75rem;
    font-size: 0.8rem;
    font-weight: 600;
    white-space: nowrap;
  }

  .no-metrics {
    text-align: center;
    padding: 2.5rem 1rem;
    color: #6b7280;
  }

  .no-metrics p {
    margin: 0;
    font-size: 1rem;
    color: #111827;
  }

  .no-metrics small {
    display: block;
    margin-top: 0.5rem;
  }

  .metric-selector {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
    margin-bottom: 1rem;
  }

  .metric-chip {
    --metric-color: #2563eb;
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    border-radius: 999px;
    border: 1px solid #d1d5db;
    background: #f9fafb;
    color: #374151;
    padding: 0.5rem 0.85rem;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .metric-chip:hover {
    border-color: var(--metric-color);
    background: #ffffff;
  }

  .metric-chip.active {
    border-color: var(--metric-color);
    background: color-mix(in srgb, var(--metric-color) 12%, white);
    color: #111827;
  }

  .metric-dot {
    width: 0.65rem;
    height: 0.65rem;
    border-radius: 999px;
    background: var(--metric-color, #2563eb);
    flex-shrink: 0;
  }

  .metric-badge {
    background: rgba(17, 24, 39, 0.08);
    border-radius: 999px;
    padding: 0.15rem 0.45rem;
    font-size: 0.75rem;
    font-weight: 600;
  }

  .summary-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
    gap: 0.9rem;
    margin-bottom: 1rem;
  }

  .summary-card {
    --metric-color: #2563eb;
    border: 1px solid #e5e7eb;
    border-top: 4px solid var(--metric-color);
    border-radius: 10px;
    background: #ffffff;
    padding: 1rem;
  }

  .summary-header {
    display: flex;
    justify-content: space-between;
    gap: 0.75rem;
    align-items: center;
  }

  .summary-name {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    font-weight: 600;
    color: #111827;
  }

  .summary-count {
    font-size: 0.75rem;
    color: #6b7280;
  }

  .summary-value {
    font-size: 1.6rem;
    font-weight: 700;
    color: #111827;
    margin-top: 0.6rem;
  }

  .summary-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 0.6rem;
    margin-top: 0.6rem;
    color: #6b7280;
    font-size: 0.8rem;
  }

  .summary-trend {
    margin-top: 0.75rem;
    display: inline-flex;
    padding: 0.25rem 0.55rem;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 700;
    background: #f3f4f6;
    color: #4b5563;
  }

  .summary-trend.up {
    background: #ecfdf5;
    color: #047857;
  }

  .summary-trend.down {
    background: #fef2f2;
    color: #b91c1c;
  }

  .chart-shell {
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    padding: 1rem;
    background: #fbfdff;
    margin-bottom: 1rem;
  }

  .chart-heading h4 {
    margin: 0;
    font-size: 0.95rem;
    color: #111827;
  }

  .chart-heading p {
    margin: 0.35rem 0 0.9rem;
    color: #6b7280;
    font-size: 0.82rem;
  }

  .metric-chart {
    width: 100%;
    height: 320px;
    display: block;
    overflow: visible;
  }

  .grid-line {
    stroke: #e5e7eb;
    stroke-width: 1;
  }

  .axis-label {
    fill: #6b7280;
    font-size: 12px;
    text-anchor: end;
  }

  .chart-point {
    opacity: 0.92;
  }

  .recent-values {
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    background: #ffffff;
    padding: 1rem;
  }

  .recent-header {
    display: flex;
    justify-content: space-between;
    gap: 0.75rem;
    align-items: center;
    margin-bottom: 0.85rem;
  }

  .recent-header h4 {
    margin: 0;
    font-size: 0.95rem;
    color: #111827;
  }

  .recent-header span {
    color: #6b7280;
    font-size: 0.8rem;
  }

  .values-table {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .value-row {
    display: grid;
    grid-template-columns: minmax(0, 1.5fr) auto auto auto;
    gap: 0.75rem;
    align-items: center;
    border-radius: 8px;
    background: #f9fafb;
    padding: 0.65rem 0.75rem;
    font-size: 0.82rem;
  }

  .value-metric {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    min-width: 0;
    color: #111827;
    font-weight: 600;
  }

  .value-number {
    font-weight: 700;
    color: #111827;
  }

  .value-job,
  .value-time {
    color: #6b7280;
    white-space: nowrap;
  }

  @media (max-width: 768px) {
    .metrics-container {
      padding: 1rem;
    }

    .metrics-header,
    .recent-header {
      flex-direction: column;
      align-items: flex-start;
    }

    .metric-selector {
      gap: 0.5rem;
    }

    .metric-chip {
      width: 100%;
      justify-content: space-between;
    }

    .metric-chart {
      height: 260px;
    }

    .value-row {
      grid-template-columns: 1fr 1fr;
    }
  }
</style>
