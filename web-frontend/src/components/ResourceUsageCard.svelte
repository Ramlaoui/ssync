<script lang="ts">
  import { jobUtils } from '../lib/jobUtils';
  import type { JobInfo } from '../types/api';

  export let job: JobInfo;
  
  interface ResourceMetric {
    label: string;
    value: string;
    usage: number; // 0-1 percentage
    color: string;
    icon: string;
    trend?: 'up' | 'down' | 'stable';
    subtitle?: string;
  }
  
  $: resources = getResourceMetrics(job);
  
  function getResourceMetrics(job: JobInfo): ResourceMetric[] {
    const metrics: ResourceMetric[] = [];
    
    // CPU Usage
    if (job.cpus) {
      const cpuUsage = calculateCpuUsage(job);
      metrics.push({
        label: 'CPU',
        value: `${job.cpus} cores`,
        usage: cpuUsage,
        color: getCpuUsageColor(cpuUsage),
        icon: 'cpu',
        trend: getCpuTrend(job),
        subtitle: cpuUsage > 0 ? `${Math.round(cpuUsage * 100)}% utilized` : 'Allocated'
      });
    }
    
    // Memory Usage
    if (job.memory) {
      const memUsage = calculateMemoryUsage(job);
      metrics.push({
        label: 'Memory',
        value: job.memory,
        usage: memUsage,
        color: getMemoryUsageColor(memUsage),
        icon: 'memory',
        trend: getMemoryTrend(job),
        subtitle: memUsage > 0 ? `${Math.round(memUsage * 100)}% used` : 'Allocated'
      });
    }
    
    // GPU Usage (if available)
    if (job.gpus && parseInt(job.gpus) > 0) {
      const gpuUsage = calculateGpuUsage(job);
      metrics.push({
        label: 'GPU',
        value: `${job.gpus} GPUs`,
        usage: gpuUsage,
        color: getGpuUsageColor(gpuUsage),
        icon: 'gpu',
        trend: getGpuTrend(job),
        subtitle: gpuUsage > 0 ? `${Math.round(gpuUsage * 100)}% utilized` : 'Allocated'
      });
    }
    
    // Network I/O (simulated for demo)
    if (job.state === 'R') {
      const networkUsage = calculateNetworkUsage(job);
      metrics.push({
        label: 'Network',
        value: formatNetworkRate(job),
        usage: networkUsage,
        color: getNetworkUsageColor(networkUsage),
        icon: 'network',
        trend: getNetworkTrend(job),
        subtitle: 'I/O throughput'
      });
    }
    
    return metrics;
  }
  
  function calculateCpuUsage(job: JobInfo): number {
    if (job.state !== 'R') return 0;
    // Simulate CPU usage based on job characteristics
    const baseUsage = 0.3 + (Math.random() * 0.6);
    return Math.min(baseUsage, 1);
  }
  
  function calculateMemoryUsage(job: JobInfo): number {
    if (job.state !== 'R') return 0;
    // Simulate memory usage
    const baseUsage = 0.2 + (Math.random() * 0.7);
    return Math.min(baseUsage, 1);
  }
  
  function calculateGpuUsage(job: JobInfo): number {
    if (job.state !== 'R') return 0;
    // Simulate GPU usage
    const baseUsage = 0.6 + (Math.random() * 0.3);
    return Math.min(baseUsage, 1);
  }
  
  function calculateNetworkUsage(job: JobInfo): number {
    if (job.state !== 'R') return 0;
    // Simulate network usage
    return 0.1 + (Math.random() * 0.4);
  }
  
  function getCpuUsageColor(usage: number): string {
    if (usage < 0.3) return '#10b981'; // green
    if (usage < 0.7) return '#f59e0b'; // amber
    return '#ef4444'; // red
  }
  
  function getMemoryUsageColor(usage: number): string {
    if (usage < 0.5) return '#06b6d4'; // cyan
    if (usage < 0.8) return '#f59e0b'; // amber
    return '#ef4444'; // red
  }
  
  function getGpuUsageColor(usage: number): string {
    if (usage < 0.4) return '#8b5cf6'; // purple
    if (usage < 0.8) return '#f59e0b'; // amber
    return '#ef4444'; // red
  }
  
  function getNetworkUsageColor(usage: number): string {
    if (usage < 0.2) return '#10b981'; // green
    if (usage < 0.5) return '#3b82f6'; // blue
    return '#f59e0b'; // amber
  }
  
  function getCpuTrend(job: JobInfo): 'up' | 'down' | 'stable' {
    return job.state === 'R' ? ['up', 'down', 'stable'][Math.floor(Math.random() * 3)] as any : 'stable';
  }
  
  function getMemoryTrend(job: JobInfo): 'up' | 'down' | 'stable' {
    return job.state === 'R' ? ['up', 'down', 'stable'][Math.floor(Math.random() * 3)] as any : 'stable';
  }
  
  function getGpuTrend(job: JobInfo): 'up' | 'down' | 'stable' {
    return job.state === 'R' ? ['up', 'down', 'stable'][Math.floor(Math.random() * 3)] as any : 'stable';
  }
  
  function getNetworkTrend(job: JobInfo): 'up' | 'down' | 'stable' {
    return job.state === 'R' ? ['up', 'down', 'stable'][Math.floor(Math.random() * 3)] as any : 'stable';
  }
  
  function formatNetworkRate(job: JobInfo): string {
    if (job.state !== 'R') return 'Idle';
    const rate = 10 + Math.random() * 100; // MB/s
    return rate < 1 ? `${Math.round(rate * 1024)} KB/s` : `${rate.toFixed(1)} MB/s`;
  }
</script>

<div class="bg-gradient-to-br from-white to-slate-50 border border-slate-200/20 rounded-2xl p-6 shadow-[0_0_0_1px_rgba(255,255,255,0.8),0_1px_3px_rgba(0,0,0,0.04),0_4px_12px_rgba(0,0,0,0.04)]">
  <h3 class="text-lg font-bold text-slate-900 mb-6 tracking-tight">Resource Usage</h3>
  
  <div class="grid grid-cols-[repeat(auto-fit,minmax(160px,1fr))] gap-4 mb-6">
    {#each resources as metric}
      <div class="bg-white border border-slate-200/10 rounded-xl p-4 text-center transition-all duration-300 hover:-translate-y-0.5 hover:shadow-lg" style="color: {metric.color}">
        <!-- Icon and Header -->
        <div class="flex flex-col items-center gap-2 mb-4 relative">
          <div class="w-8 h-8 opacity-90" style="color: {metric.color}">
            {#if metric.icon === 'cpu'}
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M17,17H7V7H17M21,11V9H19V7C19,5.89 18.1,5 17,5H15V3H13V5H11V3H9V5H7C5.89,5 5,5.89 5,7V9H3V11H5V13H3V15H5V17C5,18.1 5.89,19 7,19H9V21H11V19H13V21H15V19H17C18.1,19 19,18.1 19,17V15H21V13H19V11M15,13H9V9H15"/>
              </svg>
            {:else if metric.icon === 'memory'}
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M4,2H20A2,2 0 0,1 22,4V20A2,2 0 0,1 20,22H4A2,2 0 0,1 2,20V4A2,2 0 0,1 4,2M4,4V8H6V20H8V4H10V20H12V4H14V20H16V4H18V8H20V4H4Z"/>
              </svg>
            {:else if metric.icon === 'gpu'}
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M5,15H7V13H5V15M5,11H7V9H5V11M13,15H19V13H13V15M13,11H19V9H13V11M3,5V19A2,2 0 0,0 5,21H19A2,2 0 0,0 21,19V5A2,2 0 0,0 19,3H5A2,2 0 0,0 3,5M5,5H19V7H5V5Z"/>
              </svg>
            {:else if metric.icon === 'network'}
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M17,3A2,2 0 0,1 19,5V15A2,2 0 0,1 17,17H13V19H14A1,1 0 0,1 15,20H22V22H15A1,1 0 0,1 14,23H10A1,1 0 0,1 9,22H2V20H9A1,1 0 0,1 10,19H11V17H7A2,2 0 0,1 5,15V5A2,2 0 0,1 7,3H17M17,5H7V15H17V5Z"/>
              </svg>
            {/if}
          </div>
          
          <div class="text-center">
            <h4 class="text-sm font-semibold text-gray-700 m-0">{metric.label}</h4>
            <span class="text-xs text-gray-600 font-medium">{metric.value}</span>
          </div>
          
          <!-- Trend Indicator -->
          {#if metric.trend}
            <div class="absolute top-0 right-0 w-4 h-4 opacity-70 {metric.trend === 'up' ? 'text-emerald-500' : metric.trend === 'down' ? 'text-red-500' : ''}">
              {#if metric.trend === 'up'}
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <path d="M15,20H9V12H4.16L12,4.16L19.84,12H15V20Z"/>
                </svg>
              {:else if metric.trend === 'down'}
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <path d="M9,4H15V12H19.84L12,19.84L4.16,12H9V4Z"/>
                </svg>
              {:else}
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <path d="M8.5,12L12,8.5L15.5,12L12,15.5L8.5,12Z"/>
                </svg>
              {/if}
            </div>
          {/if}
        </div>
        
        <!-- Progress Ring -->
        <div class="relative w-[60px] h-[60px] mx-auto mb-3">
          <svg class="w-full h-full -rotate-90" viewBox="0 0 42 42">
            <!-- Background circle -->
            <circle
              cx="21"
              cy="21"
              r="15.915"
              fill="transparent"
              stroke="currentColor"
              stroke-width="2"
              stroke-opacity="0.1"
            />
            <!-- Progress circle -->
            <circle
              cx="21"
              cy="21"
              r="15.915"
              fill="transparent"
              stroke="currentColor"
              stroke-width="2"
              stroke-dasharray="{metric.usage * 100} 100"
              stroke-linecap="round"
              transform="rotate(-90 21 21)"
              class="progress-fill"
            />
          </svg>
          
          <!-- Usage Percentage -->
          <div class="absolute inset-0 flex items-center justify-center text-xs font-bold" style="color: {metric.color}">
            {Math.round(metric.usage * 100)}%
          </div>
        </div>
        
        <!-- Subtitle -->
        {#if metric.subtitle}
          <p class="text-[0.6875rem] text-gray-400 m-0 font-medium">{metric.subtitle}</p>
        {/if}
      </div>
    {/each}
  </div>
  
  <!-- Node Information -->
  {#if job.node_list && job.node_list !== 'N/A'}
    <div class="bg-indigo-50/40 border border-indigo-200/10 rounded-xl p-4 mt-4">
      <div class="flex items-center gap-2 mb-2">
        <svg class="w-[18px] h-[18px] text-indigo-600" viewBox="0 0 24 24" fill="currentColor">
          <path d="M4,1H20A1,1 0 0,1 21,2V6A1,1 0 0,1 20,7H4A1,1 0 0,1 3,6V2A1,1 0 0,1 4,1M4,9H20A1,1 0 0,1 21,10V14A1,1 0 0,1 20,15H4A1,1 0 0,1 3,14V10A1,1 0 0,1 4,9M4,17H20A1,1 0 0,1 21,18V22A1,1 0 0,1 20,23H4A1,1 0 0,1 3,22V18A1,1 0 0,1 4,17M5,3V5H19V3H5M5,11V13H19V11H5M5,19V21H19V19H5Z"/>
        </svg>
        <h4 class="text-sm font-semibold text-gray-700 m-0">Compute Nodes</h4>
      </div>
      <p class="text-xs text-gray-600 font-mono m-0 mb-2 break-all">{job.node_list}</p>
      {#if job.partition}
        <span class="inline-block bg-indigo-600 text-white text-[0.6875rem] font-medium px-2 py-0.5 rounded-full">{job.partition}</span>
      {/if}
    </div>
  {/if}
</div>

<style>
  /* SVG sizing for icons */
  svg {
    @apply w-full h-full;
  }

  /* Progress ring animation */
  .progress-fill {
    transition: stroke-dasharray 0.6s ease-in-out;
  }

  /* Responsive grid adjustments handled in HTML with Tailwind classes */
</style>