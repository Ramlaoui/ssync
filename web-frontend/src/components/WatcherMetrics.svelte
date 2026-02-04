<script lang="ts">
  import { run } from 'svelte/legacy';

  import { onMount, onDestroy } from 'svelte';
  import type { WatcherEvent } from '../types/watchers';
  
  interface Props {
    events?: WatcherEvent[];
  }

  let { events = [] }: Props = $props();
  
  // Metric state
  let selectedMetric: string | null = $state(null);
  let chartCanvas: HTMLCanvasElement | null = $state(null);
  let chartContext: CanvasRenderingContext2D | null = $state(null);
  
  
  interface Metric {
    name: string;
    value: number;
    timestamp: string;
    job_id: string;
    watcher_name: string;
  }

  // Extract metrics from events
  let metrics = $derived(extractMetrics(events));
  let metricNames = $derived(Array.from(new Set(metrics.map((m) => m.name))));
  let selectedMetricData = $derived(
    selectedMetric ? metrics.filter((m) => m.name === selectedMetric) : [],
  );
  let stats = $derived(selectedMetric ? getMetricStats(selectedMetricData) : null);
  
  function extractMetrics(events: WatcherEvent[]): Metric[] {
    return events
      .filter(e => e.action_type === 'store_metric' && e.captured_vars)
      .map(e => ({
        name: e.captured_vars.name || e.captured_vars.metric_name || 'unknown',
        value: parseFloat(e.captured_vars.value || e.captured_vars.metric_value || '0'),
        timestamp: e.timestamp,
        job_id: e.job_id,
        watcher_name: e.watcher_name
      }))
      .filter(m => !isNaN(m.value));
  }
  
  function getMetricStats(data: Metric[]) {
    if (data.length === 0) return null;
    
    const values = data.map(d => d.value);
    const sum = values.reduce((a, b) => a + b, 0);
    const avg = sum / values.length;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const latest = data[data.length - 1]?.value || 0;
    
    // Calculate trend (simple linear regression)
    const n = Math.min(data.length, 10); // Last 10 points
    const recentData = data.slice(-n);
    let trend = 'stable';
    
    if (n >= 2) {
      const firstValue = recentData[0].value;
      const lastValue = recentData[n - 1].value;
      const change = ((lastValue - firstValue) / firstValue) * 100;
      
      if (change > 5) trend = 'up';
      else if (change < -5) trend = 'down';
    }
    
    return { avg, min, max, latest, trend, count: data.length };
  }
  
  function drawChart() {
    if (!chartCanvas || !selectedMetricData.length) return;
    
    const ctx = chartCanvas.getContext('2d');
    if (!ctx) return;
    
    chartContext = ctx;
    
    const width = chartCanvas.width;
    const height = chartCanvas.height;
    const padding = 40;
    
    // Clear canvas
    ctx.clearRect(0, 0, width, height);
    
    // Set up styles
    ctx.strokeStyle = 'var(--accent)';
    ctx.fillStyle = 'var(--accent)';
    ctx.lineWidth = 2;
    
    const data = selectedMetricData.slice(-50); // Show last 50 points
    const values = data.map((d: Metric) => d.value);
    const minValue = Math.min(...values) * 0.9;
    const maxValue = Math.max(...values) * 1.1;
    const valueRange = maxValue - minValue || 1;
    
    // Draw grid
    ctx.strokeStyle = 'var(--border)';
    ctx.lineWidth = 0.5;
    
    // Horizontal grid lines
    for (let i = 0; i <= 5; i++) {
      const y = padding + (height - 2 * padding) * (i / 5);
      ctx.beginPath();
      ctx.moveTo(padding, y);
      ctx.lineTo(width - padding, y);
      ctx.stroke();
      
      // Y-axis labels
      const value = maxValue - (valueRange * i / 5);
      ctx.fillStyle = 'var(--muted-foreground)';
      ctx.font = '12px sans-serif';
      ctx.textAlign = 'right';
      ctx.fillText(value.toFixed(2), padding - 10, y + 4);
    }
    
    // Draw line chart
    ctx.strokeStyle = 'var(--accent)';
    ctx.lineWidth = 2;
    ctx.beginPath();
    
    data.forEach((point: Metric, i: number) => {
      const x = padding + ((width - 2 * padding) * i / (data.length - 1 || 1));
      const y = padding + ((maxValue - point.value) / valueRange) * (height - 2 * padding);
      
      if (i === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    });
    
    ctx.stroke();
    
    // Draw gradient fill
    const gradient = ctx.createLinearGradient(0, padding, 0, height - padding);
    gradient.addColorStop(0, 'rgba(59, 130, 246, 0.3)');
    gradient.addColorStop(1, 'rgba(59, 130, 246, 0.0)');
    
    ctx.fillStyle = gradient;
    ctx.beginPath();
    
    data.forEach((point: Metric, i: number) => {
      const x = padding + ((width - 2 * padding) * i / (data.length - 1 || 1));
      const y = padding + ((maxValue - point.value) / valueRange) * (height - 2 * padding);
      
      if (i === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    });
    
    ctx.lineTo(width - padding, height - padding);
    ctx.lineTo(padding, height - padding);
    ctx.closePath();
    ctx.fill();
    
    // Draw data points
    ctx.fillStyle = 'var(--accent)';
    data.forEach((point: Metric, i: number) => {
      const x = padding + ((width - 2 * padding) * i / (data.length - 1 || 1));
      const y = padding + ((maxValue - point.value) / valueRange) * (height - 2 * padding);
      
      ctx.beginPath();
      ctx.arc(x, y, 3, 0, Math.PI * 2);
      ctx.fill();
    });
  }
  
  $effect(() => {
    if (!selectedMetric && metricNames.length > 0) {
      selectedMetric = metricNames[0];
    }
  });

  onMount(() => {
    if (chartCanvas) {
      // Set canvas size
      chartCanvas.width = chartCanvas.offsetWidth;
      chartCanvas.height = chartCanvas.offsetHeight;
      drawChart();
    }
  });

  onDestroy(() => {
    // Cleanup hook reserved for future use
  });

  // Redraw when data changes
  run(() => {
    selectedMetricData;
    chartCanvas;
    if (chartCanvas) {
      drawChart();
    }
  });
</script>

<div class="metrics-container">
  <div class="metrics-header">
    <h3>Captured Metrics</h3>
    {#if metrics.length > 0}
      <span class="metric-count">{metrics.length} data points</span>
    {/if}
  </div>
  
  {#if metricNames.length === 0}
    <div class="no-metrics">
      <p>No metrics captured yet</p>
      <small>Metrics will appear here when watchers with store_metric actions are triggered</small>
    </div>
  {:else}
    <div class="metrics-content">
      <!-- Metric selector -->
      <div class="metric-selector">
        {#each metricNames as name}
          <button 
            class="metric-btn"
            class:active={selectedMetric === name}
            onclick={() => selectedMetric = name}
          >
            {name}
            <span class="metric-badge">
              {metrics.filter((m: Metric) => m.name === name).length}
            </span>
          </button>
        {/each}
      </div>
      
      {#if selectedMetric && stats}
        <!-- Statistics cards -->
        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-value">{stats.latest.toFixed(2)}</div>
            <div class="stat-label">Latest</div>
            <div class="stat-trend {stats.trend}">
              {#if stats.trend === 'up'}
                ↗ Increasing
              {:else if stats.trend === 'down'}
                ↘ Decreasing
              {:else}
                → Stable
              {/if}
            </div>
          </div>
          
          <div class="stat-card">
            <div class="stat-value">{stats.avg.toFixed(2)}</div>
            <div class="stat-label">Average</div>
          </div>
          
          <div class="stat-card">
            <div class="stat-value">{stats.min.toFixed(2)}</div>
            <div class="stat-label">Minimum</div>
          </div>
          
          <div class="stat-card">
            <div class="stat-value">{stats.max.toFixed(2)}</div>
            <div class="stat-label">Maximum</div>
          </div>
        </div>
        
        <!-- Chart -->
        <div class="chart-container">
          <canvas bind:this={chartCanvas} class="metric-chart"></canvas>
        </div>
        
        <!-- Recent values table -->
        <div class="recent-values">
          <h4>Recent Values</h4>
          <div class="values-table">
            {#each selectedMetricData.slice(-5).reverse() as metric}
              <div class="value-row">
                <span class="value-time">
                  {new Date(metric.timestamp).toLocaleTimeString()}
                </span>
                <span class="value-job">Job #{metric.job_id}</span>
                <span class="value-number">{metric.value.toFixed(2)}</span>
              </div>
            {/each}
          </div>
        </div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .metrics-container {
    background: var(--background);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 2rem;
  }
  
  .metrics-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1.5rem;
  }
  
  .metrics-header h3 {
    margin: 0;
    font-size: 1.25rem;
    color: var(--foreground);
  }
  
  .metric-count {
    background: var(--accent);
    color: white;
    padding: 0.25rem 0.75rem;
    border-radius: 12px;
    font-size: 0.875rem;
  }
  
  .no-metrics {
    text-align: center;
    padding: 3rem;
    color: var(--muted-foreground);
  }
  
  .no-metrics p {
    margin: 0 0 0.5rem 0;
    font-size: 1.1rem;
  }
  
  .metric-selector {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-bottom: 1.5rem;
  }
  
  .metric-btn {
    background: var(--secondary);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0.5rem 1rem;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    transition: all 0.2s;
  }
  
  .metric-btn:hover {
    background: white;
    border-color: var(--accent);
  }
  
  .metric-btn.active {
    background: var(--accent);
    color: white;
    border-color: var(--accent);
  }
  
  .metric-badge {
    background: rgba(0, 0, 0, 0.1);
    padding: 0.125rem 0.5rem;
    border-radius: 10px;
    font-size: 0.75rem;
  }
  
  .stats-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1rem;
    margin-bottom: 1.5rem;
  }
  
  .stat-card {
    background: var(--secondary);
    border-radius: 8px;
    padding: 1rem;
    text-align: center;
  }
  
  .stat-value {
    font-size: 1.5rem;
    font-weight: 600;
    color: var(--foreground);
  }
  
  .stat-label {
    font-size: 0.875rem;
    color: var(--muted-foreground);
    margin-top: 0.25rem;
  }
  
  .stat-trend {
    font-size: 0.75rem;
    margin-top: 0.5rem;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    background: var(--background);
  }
  
  .stat-trend.up {
    color: var(--success);
  }
  
  .stat-trend.down {
    color: var(--error);
  }
  
  .stat-trend.stable {
    color: var(--info);
  }
  
  .chart-container {
    background: var(--secondary);
    border-radius: 8px;
    padding: 1rem;
    margin-bottom: 1.5rem;
    height: 300px;
  }
  
  .metric-chart {
    width: 100%;
    height: 100%;
  }
  
  .recent-values {
    background: var(--secondary);
    border-radius: 8px;
    padding: 1rem;
  }
  
  .recent-values h4 {
    margin: 0 0 1rem 0;
    font-size: 1rem;
    color: var(--foreground);
  }
  
  .values-table {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  
  .value-row {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 1rem;
    padding: 0.5rem;
    background: var(--background);
    border-radius: 6px;
    font-size: 0.875rem;
  }
  
  .value-time {
    color: var(--muted-foreground);
  }
  
  .value-job {
    color: var(--accent);
  }
  
  .value-number {
    font-weight: 600;
    text-align: right;
  }
  
  @media (max-width: 768px) {
    .stats-grid {
      grid-template-columns: repeat(2, 1fr);
    }
    
    .value-row {
      grid-template-columns: 1fr;
      gap: 0.25rem;
    }
  }
</style>
