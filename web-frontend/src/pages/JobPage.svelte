<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { push } from "svelte-spa-router";
  import { jobStateManager } from "../lib/JobStateManager";
  import { api, apiConfig } from "../services/api";
  import { get } from "svelte/store";
  import type { JobInfo, JobOutputResponse, JobScriptResponse } from "../types/api";
  import JobSidebar from "../components/JobSidebar.svelte";
  import AttachWatchersDialog from "../components/AttachWatchersDialogImproved.svelte";
  import { resubmitStore } from "../stores/resubmit";
  import { 
    jobWebSocketStore, 
    connectJobWebSocket, 
    disconnectJobWebSocket,
    requestJobOutput 
  } from "../stores/jobWebSocket";

  export let params: { id?: string; host?: string } = {};

  let job: JobInfo | null = null;
  let loading = true;
  let error: string | null = null;
  let mounted = true;
  let sidebarCollapsed = false;
  let showMobileSidebar = false;
  let isMobile = false;
  
  // Get reactive job data from JobStateManager
  const allJobs = jobStateManager.getAllJobs();
  
  // Subscribe to job updates
  $: if (params.id && params.host && $allJobs.length > 0) {
    const currentJob = $allJobs.find(j => 
      j.job_id === params.id && j.hostname === params.host
    );
    if (currentJob && job?.state !== currentJob.state) {
      // Job state changed, update local job
      job = currentJob;
    }
  }
  
  // Tab state
  let activeTab: 'info' | 'output' | 'errors' | 'script' = 'info';
  
  // Output data
  let outputData: JobOutputResponse | null = null;
  let loadingOutput = false;
  let outputError: string | null = null;
  
  
  // Script data
  let scriptData: JobScriptResponse | null = null;
  let loadingScript = false;
  let scriptError: string | null = null;
  
  // Cancel job state
  let cancellingJob = false;
  let cancelError: string | null = null;
  
  // Scroll tracking
  let outputElement: HTMLPreElement | null = null;
  let isAtBottom = true;
  
  // Overflow menu
  let showOverflowMenu = false;
  let overflowMenuRef: HTMLDivElement;
  
  // Attach watchers dialog
  let showAttachWatchersDialog = false;

  $: canCancelJob = job && (job.state === 'R' || job.state === 'PD');


  async function loadJob(forceRefresh = false) {
    if (!params.id || !params.host) {
      error = "Invalid job parameters";
      loading = false;
      return;
    }

    // Clear previous output data to prevent showing old job's output
    outputData = null;
    outputError = null;

    try {
      loading = true;
      error = null;
      
      const fetchedJob = await jobStateManager.fetchJob(params.id, params.host);
      
      if (mounted) {
        if (fetchedJob) {
          job = fetchedJob;
          error = null;
        } else {
          error = `Job ${params.id} not found on ${params.host}`;
        }
      }
    } catch (err: any) {
      if (mounted) {
        error = `Failed to load job: ${err.message || 'Unknown error'}`;
      }
    } finally {
      if (mounted) {
        loading = false;
      }
    }
  }

  // Progressive loading variables
  let loadedChunks = 0;
  let totalSizeBytes = 0;
  let hasMoreOutput = false;
  let loadingMoreOutput = false;
  const CHUNK_SIZE = 100 * 1024; // 100KB chunks

  async function loadOutput(forceRefresh = false): Promise<void> {
    if (!job || loadingOutput) return;
    
    // Don't reload if we already have data for this job (unless force refresh)
    if (!forceRefresh && outputData && outputData.job_id === job.job_id) {
      return;
    }
    
    loadingOutput = true;
    outputError = null;
    
    // Reset progressive loading state
    loadedChunks = 0;
    hasMoreOutput = false;
    loadingMoreOutput = false;
    
    try {
      // Start with a reasonable chunk size for initial load
      const initialLines = 1000;
      const response = await api.get<JobOutputResponse>(
        `/api/jobs/${job.job_id}/output?host=${encodeURIComponent(job.hostname)}&lines=${initialLines}${forceRefresh ? '&force_refresh=true' : ''}`
      );
      
      outputData = response.data;
      
      if (!outputData) {
        outputError = 'No output data available';
        return;
      }
      
      // Estimate if there might be more content based on response size
      const stdoutSize = outputData.stdout?.length || 0;
      const stderrSize = outputData.stderr?.length || 0;
      const totalSize = stdoutSize + stderrSize;
      
      // If we got exactly the line limit and the content is substantial, 
      // assume there might be more content
      const stdoutLines = outputData.stdout ? outputData.stdout.split('\n').length : 0;
      const stderrLines = outputData.stderr ? outputData.stderr.split('\n').length : 0;
      
      // Heuristic: if we got close to our line limit and content is substantial,
      // there's probably more content available
      hasMoreOutput = (stdoutLines >= initialLines * 0.9 || stderrLines >= initialLines * 0.9) && 
                      totalSize > 10000; // At least 10KB suggests substantial content
      
      if (hasMoreOutput) {
        loadedChunks = 1;
        
      }
    } catch (error: unknown) {
      console.error('Error loading job output:', error);
      outputError = (error as Error).message || 'Failed to load output';
    } finally {
      loadingOutput = false;
    }
  }

  function formatFileSize(bytes: number): string {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  }

  async function loadMoreOutput(): Promise<void> {
    if (!job || !hasMoreOutput || loadingMoreOutput || !outputData) return;
    
    loadingMoreOutput = true;
    
    try {
      // Load more chunks by increasing the line count
      const newLineLimit = 1000 + (loadedChunks * 500); // Gradually increase
      const response = await api.get<JobOutputResponse>(
        `/api/jobs/${job.job_id}/output?host=${encodeURIComponent(job.hostname)}&lines=${newLineLimit}`
      );
      
      if (response.data) {
        // Check if we got more content
        const newStdoutSize = response.data.stdout?.length || 0;
        const newStderrSize = response.data.stderr?.length || 0;
        const currentStdoutSize = outputData.stdout?.length || 0;
        const currentStderrSize = outputData.stderr?.length || 0;
        
        if (newStdoutSize > currentStdoutSize || newStderrSize > currentStderrSize) {
          outputData = response.data;
          loadedChunks++;
        } else {
          // No more content available
          hasMoreOutput = false;
        }
        
        // Check if we've loaded most of the file
        if (newLineLimit >= 5000) {
          hasMoreOutput = false;
        }
      }
    } catch (error) {
      console.error('Error loading more output:', error);
    } finally {
      loadingMoreOutput = false;
    }
  }

  async function loadScript(): Promise<void> {
    if (!job || loadingScript) return;
    
    // Don't reload if we already have data for this job
    if (scriptData && scriptData.job_id === job.job_id) {
      return;
    }
    
    loadingScript = true;
    scriptError = null;
    
    try {
      const response = await api.get<JobScriptResponse>(`/api/jobs/${job.job_id}/script?host=${encodeURIComponent(job.hostname)}`);
      scriptData = response.data;
    } catch (error: unknown) {
      console.error('Error loading job script:', error);
      scriptError = (error as Error).message || 'Failed to load script';
    } finally {
      loadingScript = false;
    }
  }

  function retryLoadOutput(): void {
    outputData = null;
    outputError = null;
    loadOutput(true); // Force refresh on retry
  }

  function retryLoadScript(): void {
    scriptData = null;
    scriptError = null;
    loadScript();
  }
  
  // Watch for tab changes to load data as needed
  $: if (job && activeTab) {
    if ((activeTab === 'output' || activeTab === 'errors') && (!outputData || outputData.job_id !== job.job_id)) {
      loadOutput();
    } else if (activeTab === 'script' && (!scriptData || scriptData.job_id !== job.job_id)) {
      loadScript();
    }
  }

  function handleClose() {
    push('/');
  }

  function handleRefresh() {
    loadJob(true);
    // Also refresh output if it's currently displayed
    if (activeTab === 'output' || activeTab === 'errors') {
      outputData = null; // Clear cached data
      loadOutput(true);
    }
    // Also refresh script if it's currently displayed
    if (activeTab === 'script') {
      scriptData = null; // Clear cached data
      loadScript();
    }
  }

  async function cancelJob(): Promise<void> {
    if (!job || cancellingJob) return;
    
    const confirmed = confirm(`Are you sure you want to cancel job ${job.job_id}?`);
    if (!confirmed) return;
    
    cancellingJob = true;
    cancelError = null;
    
    try {
      await api.post(`/api/jobs/${job.job_id}/cancel?host=${encodeURIComponent(job.hostname)}`);
      job.state = 'CA';
      alert(`Job ${job.job_id} has been cancelled successfully.`);
    } catch (error: unknown) {
      console.error('Error cancelling job:', error);
      cancelError = (error as Error).message || 'Failed to cancel job';
      alert(`Failed to cancel job: ${cancelError}`);
    } finally {
      cancellingJob = false;
    }
  }

  function formatTime(timeStr: string | null): string {
    if (!timeStr || timeStr === 'N/A') return 'N/A';
    try {
      return new Date(timeStr).toLocaleString();
    } catch {
      return timeStr;
    }
  }

  function getStateColor(state: string): string {
    switch (state) {
      case 'R': return '#10b981';
      case 'PD': return '#f59e0b';
      case 'CD': return '#8b5cf6';
      case 'F': return '#ef4444';
      case 'CA': return '#6b7280';
      case 'TO': return '#f97316';
      default: return '#06b6d4';
    }
  }

  function getStateLabel(state: string): string {
    switch (state) {
      case 'R': return 'RUNNING';
      case 'PD': return 'PENDING';
      case 'CD': return 'COMPLETED';
      case 'F': return 'FAILED';
      case 'CA': return 'CANCELLED';
      case 'TO': return 'TIMEOUT';
      default: return 'UNKNOWN';
    }
  }
  
  function checkScrollPosition() {
    if (!outputElement) return;
    
    const threshold = 50; // pixels from bottom
    const scrollTop = outputElement.scrollTop;
    const scrollHeight = outputElement.scrollHeight;
    const clientHeight = outputElement.clientHeight;
    
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight;
    isAtBottom = distanceFromBottom < threshold;
    
    // Load more content when scrolling near bottom
    if (distanceFromBottom < 200 && hasMoreOutput && !loadingMoreOutput) {
      loadMoreOutput();
    }
  }
  
  function scrollToBottom() {
    if (!outputElement) return;
    outputElement.scrollTop = outputElement.scrollHeight;
    isAtBottom = true;
  }
  
  function scrollToTop() {
    if (!outputElement) return;
    outputElement.scrollTop = 0;
    isAtBottom = false;
  }
  
  function toggleOverflowMenu() {
    showOverflowMenu = !showOverflowMenu;
  }
  
  function closeOverflowMenu() {
    showOverflowMenu = false;
  }
  
  function handleClickOutside(event: MouseEvent) {
    if (overflowMenuRef && !overflowMenuRef.contains(event.target as Node)) {
      closeOverflowMenu();
    }
  }
  
  function handleCancelJob() {
    closeOverflowMenu();
    cancelJob();
  }
  
  async function downloadScript() {
    if (!job) return;
    
    try {
      const config = get(apiConfig);
      const headers: HeadersInit = {};
      if (config.apiKey) {
        headers['X-API-Key'] = config.apiKey;
      }
      
      const response = await fetch(`/api/jobs/${job.job_id}/script?host=${job.hostname}`, {
        headers
      });
      
      if (!response.ok) throw new Error('Failed to fetch script');
      
      const data = await response.json();
      if (data.script_content) {
        const blob = new Blob([data.script_content], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `job_${job.job_id}_script.sh`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }
    } catch (error) {
      console.error('Failed to download script:', error);
    }
  }
  
  async function downloadOutput() {
    if (!job) return;
    
    try {
      const config = get(apiConfig);
      const headers: HeadersInit = {};
      if (config.apiKey) {
        headers['X-API-Key'] = config.apiKey;
      }
      
      const response = await fetch(`/api/jobs/${job.job_id}/output?host=${job.hostname}&metadata_only=false`, {
        headers
      });
      
      if (!response.ok) throw new Error('Failed to fetch output');
      
      const data = await response.json();
      const output = [];
      
      if (data.stdout) {
        output.push('=== STDOUT ===\n');
        output.push(data.stdout);
        output.push('\n\n');
      }
      
      if (data.stderr) {
        output.push('=== STDERR ===\n');
        output.push(data.stderr);
      }
      
      if (output.length > 0) {
        const blob = new Blob([output.join('')], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `job_${job.job_id}_output.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }
    } catch (error) {
      console.error('Failed to download output:', error);
    }
  }
  
  function parseSubmitLine(submitLine: string): Record<string, string> {
    const params: Record<string, string> = {};
    
    // Match patterns like --partition=gpu, --time=1:00:00, --mem 32G, etc.
    const patterns = [
      /--([a-z-]+)=([^\s]+)/gi,  // --key=value
      /--([a-z-]+)\s+([^\s-]+)/gi  // --key value
    ];
    
    for (const pattern of patterns) {
      let match;
      while ((match = pattern.exec(submitLine)) !== null) {
        const [, key, value] = match;
        // Normalize key names (e.g., cpus-per-task -> cpus_per_task)
        const normalizedKey = key.replace(/-/g, '_');
        params[normalizedKey] = value;
      }
    }
    
    return params;
  }
  
  function mergeParametersIntoScript(scriptContent: string, submitLine: string | null): string {
    if (!submitLine) return scriptContent;
    
    console.log('Original submit line:', submitLine);
    const submitParams = parseSubmitLine(submitLine);
    console.log('Parsed submit parameters:', submitParams);
    
    // Extract existing #SBATCH directives from script
    const existingDirectives = new Set<string>();
    const lines = scriptContent.split('\n');
    
    lines.forEach(line => {
      const match = line.match(/#SBATCH\s+--([a-z-]+)/i);
      if (match) {
        existingDirectives.add(match[1].replace(/-/g, '_'));
      }
    });
    
    // Build new #SBATCH lines for parameters not in script
    const newDirectives: string[] = [];
    for (const [key, value] of Object.entries(submitParams)) {
      if (!existingDirectives.has(key)) {
        // Convert back to SLURM format
        const slurmKey = key.replace(/_/g, '-');
        newDirectives.push(`#SBATCH --${slurmKey}=${value}`);
      }
    }
    
    if (newDirectives.length === 0) {
      return scriptContent;
    }
    
    // Insert new directives after shebang but before other content
    const shebangIndex = lines.findIndex(line => line.startsWith('#!'));
    const insertIndex = shebangIndex >= 0 ? shebangIndex + 1 : 0;
    
    // Add a comment to indicate these were from the original submission
    const comment = '\n# Parameters from original job submission:';
    lines.splice(insertIndex, 0, comment, ...newDirectives, '');
    
    return lines.join('\n');
  }

  function attachWatchers() {
    closeOverflowMenu();
    showAttachWatchersDialog = true;
  }
  
  async function resubmitJob() {
    if (!job) {
      console.error('No job data available');
      return;
    }
    
    console.log('Starting resubmit for job:', job.job_id);
    console.log('Job submit_line:', job.submit_line);
    closeOverflowMenu();
    
    // Load the script if not already loaded
    if (!scriptData || !scriptData.script_content) {
      console.log('Loading script...');
      await loadScript();
    }
    
    // Check again after loading
    if (!scriptData || !scriptData.script_content) {
      console.error('Failed to load script for resubmission', scriptData);
      error = 'Failed to load job script for resubmission';
      return;
    }
    
    console.log('Script loaded, merging submit parameters...');
    
    // Merge submit line parameters into script
    const mergedScript = mergeParametersIntoScript(
      scriptData.script_content,
      job.submit_line
    );
    
    // Store the resubmit data
    const resubmitData = {
      scriptContent: mergedScript,
      hostname: job.hostname,
      workDir: job.work_dir || undefined,
      originalJobId: job.job_id,
      jobName: job.name,
      submitLine: job.submit_line || undefined
    };
    
    console.log('Resubmit data with merged parameters:', resubmitData);
    resubmitStore.setResubmitData(resubmitData);
    
    // Navigate to the launch page
    console.log('Navigating to /launch');
    push('/launch');
  }

  // Subscribe to WebSocket updates
  $: if ($jobWebSocketStore.connected && $jobWebSocketStore.job) {
    // Only update if it's the same job we're viewing
    if ($jobWebSocketStore.job.job_id === params.id && 
        (!params.host || $jobWebSocketStore.job.hostname === params.host)) {
      job = $jobWebSocketStore.job;
    }
    
    // Check for output updates
    const latestUpdate = $jobWebSocketStore.updates[$jobWebSocketStore.updates.length - 1];
    if (latestUpdate?.type === 'output_update' && activeTab === 'output') {
      // Append new output to existing output
      if (outputData) {
        outputData = {
          ...outputData,
          stdout: outputData.stdout + (latestUpdate.data.content || '')
        };
      }
    }
  }

  onMount(() => {
    mounted = true;
    loadJob();
    
    // JobStateManager handles WebSocket connection automatically
    // Just ensure we sync this specific job
    if (params.id && params.host) {
      jobStateManager.syncHost(params.host);
    }
    
    // Check if mobile
    checkMobile();
    window.addEventListener('resize', checkMobile);
    
    // Add click outside listener for overflow menu
    document.addEventListener('click', handleClickOutside);
    
    // Load collapsed state from localStorage
    const saved = localStorage.getItem('jobSidebarCollapsed');
    if (saved) {
      sidebarCollapsed = saved === 'true';
    }
    
    // No need for auto-refresh with WebSocket
    // DataSyncManager and WebSocket handle all automatic refreshing
    // No need for fallback polling intervals
  });
  
  function checkMobile() {
    isMobile = window.innerWidth < 768;
    if (isMobile) {
      sidebarCollapsed = false; // Don't collapse on mobile
    }
  }

  onDestroy(() => {
    mounted = false;
    
    // Clear all data to prevent memory leaks
    outputData = null;
    scriptData = null;
    
    // Clean up event listeners
    try {
      window.removeEventListener('resize', checkMobile);
      document.removeEventListener('click', handleClickOutside);
    } catch (e) {
      console.warn('Error removing event listeners:', e);
    }
    
    // JobStateManager handles WebSocket cleanup automatically
  });
  
  function toggleSidebar() {
    sidebarCollapsed = !sidebarCollapsed;
    localStorage.setItem('jobSidebarCollapsed', String(sidebarCollapsed));
  }

  // Track params changes
  let lastParams = { id: params.id, host: params.host };
  
  $: if (mounted && params.id && params.host && 
      (params.id !== lastParams.id || params.host !== lastParams.host)) {
    lastParams = { id: params.id, host: params.host };
    // Reset data when switching jobs
    outputData = null;
    scriptData = null;
    outputError = null;
    scriptError = null;
    // Disconnect old WebSocket first
    disconnectJobWebSocket();
    loadJob();
    // Connect WebSocket for new job immediately (no delay to prevent race conditions)
    if (params.id) {
      connectJobWebSocket(params.id, params.host);
    }
  }
  
  // Reactive statements need to check job ID to re-trigger on job change
  $: if (job && (activeTab === 'output' || activeTab === 'errors')) {
    // Check if we need to load output for this specific job
    if (!outputData || outputData.job_id !== job.job_id) {
      loadOutput();
    }
  }
  
  $: if (job && activeTab === 'script') {
    // Check if we need to load script for this specific job
    if (!scriptData || scriptData.job_id !== job.job_id) {
      loadScript();
    }
  }
</script>

<div class="job-page">
  {#if isMobile && showMobileSidebar}
    <!-- Mobile Sidebar Overlay -->
    <div class="mobile-sidebar-overlay">
      <JobSidebar 
        currentJobId={params.id || ''}
        currentHost={params.host || ''}
        collapsed={false}
        {isMobile}
        onMobileJobSelect={() => showMobileSidebar = false}
      />
      <button 
        class="mobile-toggle-btn"
        on:click={() => showMobileSidebar = false}
      >
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"/>
        </svg>
        Close List
      </button>
    </div>
  {:else}
    <div class="page-layout" class:sidebar-collapsed={sidebarCollapsed}>
      {#if !isMobile}
        <!-- Desktop Sidebar -->
        <JobSidebar 
          currentJobId={params.id || ''}
          currentHost={params.host || ''}
          bind:collapsed={sidebarCollapsed}
          {isMobile}
        />
      {/if}
      
      <div class="job-content-area">
        <!-- Header -->
        <div class="header">
    <div class="header-left">
      {#if isMobile}
        <button 
          class="mobile-sidebar-btn" 
          on:click={() => showMobileSidebar = true}
          aria-label="Show job list"
        >
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M3,6H21V8H3V6M3,11H21V13H3V11M3,16H21V18H3V16Z"/>
          </svg>
        </button>
      {:else}
        <button class="back-btn" on:click={handleClose} aria-label="Back">
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M20,11V13H8L13.5,18.5L12.08,19.92L4.16,12L12.08,4.08L13.5,5.5L8,11H20Z"/>
          </svg>
          Jobs
        </button>
      {/if}
      {#if job}
      <div class="divider"></div>
      <div class="job-title">
        <span class="job-label">{params.host}</span>
        <span class="separator">/</span>
        <span class="job-label">Job {job.job_id}</span>
        <span class="job-name">{job.name}</span>
      </div>
      {/if}
    </div>
    
    <div class="header-right">
      <button 
        class="refresh-btn" 
        on:click={handleRefresh} 
        disabled={loading}
      >
        <svg class:spinning={loading} viewBox="0 0 24 24" fill="currentColor">
          <path d="M12,6V9L16,5L12,1V4A8,8 0 0,0 4,12C4,13.57 4.46,15.03 5.24,16.26L6.7,14.8C6.25,13.97 6,13 6,12A6,6 0 0,1 12,6M18.76,7.74L17.3,9.2C17.74,10.04 18,11 18,12A6,6 0 0,1 12,18V15L8,19L12,23V20A8,8 0 0,0 20,12C20,10.43 19.54,8.97 18.76,7.74Z" />
        </svg>
        {loading ? "Refreshing..." : "Refresh"}
      </button>
      
      {#if job}
      <div class="overflow-menu-container" bind:this={overflowMenuRef}>
        <button 
          class="overflow-btn" 
          on:click|stopPropagation={toggleOverflowMenu}
          aria-label="More actions"
        >
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M12,16A2,2 0 0,1 14,18A2,2 0 0,1 12,20A2,2 0 0,1 10,18A2,2 0 0,1 12,16M12,10A2,2 0 0,1 14,12A2,2 0 0,1 12,14A2,2 0 0,1 10,12A2,2 0 0,1 12,10M12,4A2,2 0 0,1 14,6A2,2 0 0,1 12,8A2,2 0 0,1 10,6A2,2 0 0,1 12,4Z"/>
          </svg>
        </button>
        
        {#if showOverflowMenu}
        <div class="overflow-menu" on:click|stopPropagation>
          <div class="menu-section">
            <div class="menu-label">Actions</div>
            
            <button class="menu-item" on:click={resubmitJob}>
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M17.65,6.35C16.2,4.9 14.21,4 12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20C15.73,20 18.84,17.45 19.73,14H17.65C16.83,16.33 14.61,18 12,18A6,6 0 0,1 6,12A6,6 0 0,1 12,6C13.66,6 15.14,6.69 16.22,7.78L13,11H20V4L17.65,6.35Z"/>
              </svg>
              <span>Resubmit Job</span>
            </button>
            
            {#if job && (job.state === 'R' || job.state === 'PD')}
            <button class="menu-item" on:click={attachWatchers}>
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M12,9A3,3 0 0,0 9,12A3,3 0 0,0 12,15A3,3 0 0,0 15,12A3,3 0 0,0 12,9M12,17A5,5 0 0,1 7,12A5,5 0 0,1 12,7A5,5 0 0,1 17,12A5,5 0 0,1 12,17M12,4.5C7,4.5 2.73,7.61 1,12C2.73,16.39 7,19.5 12,19.5C17,19.5 21.27,16.39 23,12C21.27,7.61 17,4.5 12,4.5Z"/>
              </svg>
              <span>Attach Watchers</span>
            </button>
            {/if}
            
            <button class="menu-item" on:click={() => {closeOverflowMenu(); navigator.clipboard.writeText(job.job_id)}}>
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M19,21H8V7H19M19,5H8A2,2 0 0,0 6,7V21A2,2 0 0,0 8,23H19A2,2 0 0,0 21,21V7A2,2 0 0,0 19,5M16,1H4A2,2 0 0,0 2,3V17H4V3H16V1Z"/>
              </svg>
              <span>Copy Job ID</span>
            </button>
            
            {#if job.work_dir}
            <button class="menu-item" on:click={() => {closeOverflowMenu(); navigator.clipboard.writeText(job.work_dir)}}>
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M10,4H4C2.89,4 2,4.89 2,6V18A2,2 0 0,0 4,20H20A2,2 0 0,0 22,18V8C22,6.89 21.1,6 20,6H12L10,4Z"/>
              </svg>
              <span>Copy Work Directory</span>
            </button>
            {/if}
            
            <button class="menu-item" on:click={() => {closeOverflowMenu(); downloadScript()}}>
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z"/>
              </svg>
              <span>Download Script</span>
            </button>
            
            <button class="menu-item" on:click={() => {closeOverflowMenu(); downloadOutput()}}>
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M5,20H19V18H5M19,9H15V3H9V9H5L12,16L19,9Z"/>
              </svg>
              <span>Download Output</span>
            </button>
          </div>
          
          {#if canCancelJob}
          <div class="menu-divider"></div>
          
          <div class="menu-section">
            <div class="menu-label">Danger Zone</div>
            
            <button class="menu-item danger" on:click={handleCancelJob} disabled={cancellingJob}>
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"/>
              </svg>
              <span>Cancel Job</span>
            </button>
          </div>
          {/if}
        </div>
        {/if}
      </div>
      
      <span class="state-badge" style="background-color: {getStateColor(job.state)}">
        {getStateLabel(job.state)}
      </span>
      {/if}
    </div>
  </div>
  
  {#if error && !job}
    <div class="error-container">
      <svg viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z" />
      </svg>
      <h2>Unable to Load Job</h2>
      <p>{error}</p>
      <button on:click={handleRefresh}>Try Again</button>
    </div>
  {:else if job}
    <!-- Modern Tab Controls -->
    <div class="content-controls">
      <!-- Tab Selection -->
      <div class="view-selection">
        <div class="tabs-left">
          <button 
            class="view-tab"
            class:active={activeTab === 'info'}
            on:click={() => activeTab = 'info'}
          >
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M11 7h2v2h-2zm0 4h2v6h-2zm1-9C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z"/>
            </svg>
            <span class="tab-label">Info</span>
          </button>
          <button 
            class="view-tab"
            class:active={activeTab === 'output'}
            on:click={() => activeTab = 'output'}
          >
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z"/>
            </svg>
            <span class="tab-label">Output</span>
          </button>
          <button 
            class="view-tab"
            class:active={activeTab === 'errors'}
            on:click={() => activeTab = 'errors'}
          >
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>
            </svg>
            <span class="tab-label">Errors</span>
          </button>
          <button 
            class="view-tab"
            class:active={activeTab === 'script'}
            on:click={() => activeTab = 'script'}
          >
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M9.4 16.6L4.8 12l4.6-4.6L8 6l-6 6 6 6 1.4-1.4zm5.2 0l4.6-4.6-4.6-4.6L16 6l6 6-6 6-1.4-1.4z"/>
            </svg>
            <span class="tab-label">Script</span>
          </button>
        </div>
        
        <!-- Tab Actions on the right -->
        <div class="tabs-right">
          {#if activeTab === 'output' || activeTab === 'errors'}
            <button 
              class="tab-action-btn"
              on:click={() => loadOutput(true)}
              disabled={loadingOutput}
              title="Refresh {activeTab === 'output' ? 'output' : 'errors'}"
            >
              <svg viewBox="0 0 24 24" fill="currentColor" class:spinning={loadingOutput}>
                <path d="M17.65,6.35C16.2,4.9 14.21,4 12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20C15.73,20 18.84,17.45 19.73,14H17.65C16.83,16.33 14.61,18 12,18A6,6 0 0,1 6,12A6,6 0 0,1 12,6C13.66,6 15.14,6.69 16.22,7.78L13,11H20V4L17.65,6.35Z"/>
              </svg>
            </button>
            <button 
              class="tab-action-btn"
              on:click={scrollToTop}
              title="Scroll to top"
            >
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M7.41,15.41L12,10.83L16.59,15.41L18,14L12,8L6,14L7.41,15.41Z"/>
              </svg>
            </button>
            <button 
              class="tab-action-btn"
              on:click={scrollToBottom}
              title="Scroll to bottom"
            >
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M7.41,8.59L12,13.17L16.59,8.59L18,10L12,16L6,10L7.41,8.59Z"/>
              </svg>
            </button>
          {:else if activeTab === 'script'}
            <button 
              class="tab-action-btn"
              on:click={() => downloadScript()}
              title="Download script"
            >
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M5,20H19V18H5M19,9H15V3H9V9H5L12,16L19,9Z"/>
              </svg>
            </button>
            <button 
              class="tab-action-btn"
              on:click={scrollToTop}
              title="Scroll to top"
            >
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M7.41,15.41L12,10.83L16.59,15.41L18,14L12,8L6,14L7.41,15.41Z"/>
              </svg>
            </button>
            <button 
              class="tab-action-btn"
              on:click={scrollToBottom}
              title="Scroll to bottom"
            >
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M7.41,8.59L12,13.17L16.59,8.59L18,10L12,16L6,10L7.41,8.59Z"/>
              </svg>
            </button>
          {/if}
        </div>
      </div>
      
    </div>
    
    <!-- Content -->
    <div class="content">
      {#if activeTab === 'info'}
        <div class="info-container">
          <!-- General Information -->
          <div class="info-card">
            <h3 class="card-title">General</h3>
            <div class="info-row">
              <span class="info-label">Job ID:</span>
              <span class="info-value">{job.job_id}</span>
            </div>
            <div class="info-row">
              <span class="info-label">Name:</span>
              <span class="info-value">{job.name}</span>
            </div>
            <div class="info-row">
              <span class="info-label">User:</span>
              <span class="info-value">{job.user || 'N/A'}</span>
            </div>
            <div class="info-row">
              <span class="info-label">Host:</span>
              <span class="info-value">{job.hostname}</span>
            </div>
            <div class="info-row">
              <span class="info-label">Partition:</span>
              <span class="info-value">{job.partition || 'N/A'}</span>
            </div>
            {#if job.account}
            <div class="info-row">
              <span class="info-label">Account:</span>
              <span class="info-value">{job.account}</span>
            </div>
            {/if}
            {#if job.qos}
            <div class="info-row">
              <span class="info-label">QoS:</span>
              <span class="info-value">{job.qos}</span>
            </div>
            {/if}
            {#if job.priority}
            <div class="info-row">
              <span class="info-label">Priority:</span>
              <span class="info-value">{job.priority}</span>
            </div>
            {/if}
            {#if job.array_job_id}
            <div class="info-row">
              <span class="info-label">Array Job:</span>
              <span class="info-value">{job.array_job_id}{job.array_task_id ? `[${job.array_task_id}]` : ''}</span>
            </div>
            {/if}
            {#if job.work_dir && job.work_dir !== 'N/A'}
            <div class="info-row full-width">
              <span class="info-label">Work Dir:</span>
              <span class="info-value mono">{job.work_dir}</span>
            </div>
            {/if}
            {#if job.reason && job.reason !== 'N/A' && job.reason !== 'None'}
            <div class="info-row full-width">
              <span class="info-label">Reason:</span>
              <span class="info-value">{job.reason}</span>
            </div>
            {/if}
            {#if job.submit_line}
            <div class="info-row full-width">
              <span class="info-label">Submit Command:</span>
              <span class="info-value mono">{job.submit_line}</span>
            </div>
            {/if}
            {#if job.exit_code && job.state !== 'R' && job.state !== 'PD'}
            <div class="info-row">
              <span class="info-label">Exit Code:</span>
              <span class="info-value" style="color: {job.exit_code === '0:0' || job.exit_code === '0' ? '#10b981' : '#ef4444'}">
                {job.exit_code}
              </span>
            </div>
            {/if}
          </div>
          
          <!-- Resources -->
          <div class="info-card">
            <h3 class="card-title">Resources</h3>
            <div class="info-row">
              <span class="info-label">Nodes:</span>
              <span class="info-value">{job.nodes || 'N/A'}</span>
            </div>
            <div class="info-row">
              <span class="info-label">CPUs:</span>
              <span class="info-value">{job.cpus || 'N/A'}</span>
            </div>
            <div class="info-row">
              <span class="info-label">Memory:</span>
              <span class="info-value">{job.memory || 'N/A'}</span>
            </div>
            {#if job.alloc_tres && job.alloc_tres.includes('gpu')}
            <div class="info-row">
              <span class="info-label">GPUs:</span>
              <span class="info-value">{job.alloc_tres.split(',').find(t => t.includes('gpu')) || 'N/A'}</span>
            </div>
            {/if}
            <div class="info-row">
              <span class="info-label">Time Limit:</span>
              <span class="info-value">{job.time_limit || 'N/A'}</span>
            </div>
            <div class="info-row">
              <span class="info-label">Runtime:</span>
              <span class="info-value">{job.runtime || '0:00'}</span>
            </div>
            {#if job.node_list && job.node_list !== 'N/A'}
            <div class="info-row full-width">
              <span class="info-label">Node List:</span>
              <span class="info-value mono">{job.node_list}</span>
            </div>
            {/if}
          </div>
          
          <!-- Timing -->
          <div class="info-card">
            <h3 class="card-title">Timing</h3>
            <div class="info-row full-width">
              <span class="info-label">Submitted:</span>
              <span class="info-value">{formatTime(job.submit_time)}</span>
            </div>
            <div class="info-row full-width">
              <span class="info-label">Started:</span>
              <span class="info-value">{formatTime(job.start_time)}</span>
            </div>
            <div class="info-row full-width">
              <span class="info-label">Ended:</span>
              <span class="info-value">{formatTime(job.end_time)}</span>
            </div>
          </div>
          
          <!-- File Paths -->
          {#if (job.stdout_file && job.stdout_file !== 'N/A') || (job.stderr_file && job.stderr_file !== 'N/A')}
          <div class="info-card">
            <h3 class="card-title">File Paths</h3>
            {#if job.stdout_file && job.stdout_file !== 'N/A'}
            <div class="info-row full-width">
              <span class="info-label">Output File:</span>
              <span class="info-value mono">{job.stdout_file}</span>
            </div>
            {/if}
            {#if job.stderr_file && job.stderr_file !== 'N/A'}
            <div class="info-row full-width">
              <span class="info-label">Error File:</span>
              <span class="info-value mono">{job.stderr_file}</span>
            </div>
            {/if}
          </div>
          {/if}
        </div>
        
      {:else if activeTab === 'output'}
        <div class="output-section">
          {#if loadingOutput}
            <div class="loading-state">
              <div class="spinner"></div>
              <span>Loading output...</span>
            </div>
          {:else if outputError}
            <div class="error-state">
              <span>{outputError}</span>
              <button class="retry-btn" on:click={retryLoadOutput}>Retry</button>
            </div>
          {:else if outputData?.stdout}
            <div class="output-container">
              <pre class="output-content" bind:this={outputElement} on:scroll={checkScrollPosition}>{outputData.stdout}</pre>
              {#if loadingMoreOutput}
                <div class="loading-more">
                  <div class="spinner"></div>
                  <span>Loading more output...</span>
                </div>
              {/if}
            </div>
          {:else}
            <div class="empty-state">
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z"/>
              </svg>
              <span>No output available</span>
            </div>
          {/if}
        </div>
        
      {:else if activeTab === 'errors'}
        <div class="output-section">
          {#if loadingOutput}
            <div class="loading-state">
              <div class="spinner"></div>
              <span>Loading errors...</span>
            </div>
          {:else if outputError}
            <div class="error-state">
              <span>{outputError}</span>
              <button class="retry-btn" on:click={retryLoadOutput}>Retry</button>
            </div>
          {:else if outputData?.stderr}
            <div class="output-container">
              <pre class="output-content error" bind:this={outputElement} on:scroll={checkScrollPosition}>{outputData.stderr}</pre>
              {#if loadingMoreOutput}
                <div class="loading-more">
                  <div class="spinner"></div>
                  <span>Loading more output...</span>
                </div>
              {/if}
            </div>
          {:else}
            <div class="empty-state">
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M12,20A8,8 0 0,0 20,12A8,8 0 0,0 12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20M12,2A10,10 0 0,1 22,12A10,10 0 0,1 12,22C6.47,22 2,17.5 2,12A10,10 0 0,1 12,2M12.5,7V12.25L17,14.92L16.25,16.15L11,13V7H12.5Z"/>
              </svg>
              <span>No errors</span>
            </div>
          {/if}
        </div>
        
      {:else if activeTab === 'script'}
        <div class="output-section">
          {#if loadingScript}
            <div class="loading-state">
              <div class="spinner"></div>
              <span>Loading script...</span>
            </div>
          {:else if scriptError}
            <div class="error-state">
              <span>{scriptError}</span>
              <button class="retry-btn" on:click={retryLoadScript}>Retry</button>
            </div>
          {:else if scriptData?.script_content}
            <pre class="output-content script" bind:this={outputElement} on:scroll={checkScrollPosition}>{scriptData.script_content}</pre>
          {:else}
            <div class="empty-state">
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M14.6,16.6L19.2,12L14.6,7.4L16,6L22,12L16,18L14.6,16.6M9.4,16.6L4.8,12L9.4,7.4L8,6L2,12L8,18L9.4,16.6Z"/>
              </svg>
              <span>Script not available</span>
            </div>
          {/if}
        </div>
      {/if}
    </div>
  {/if}
      </div>
    </div>
  {/if}
</div>

<style>
  .job-page {
    height: 100%;
    display: flex;
    flex-direction: column;
    background: #f8fafc;
  }

  /* Header */
  .header {
    background: white;
    border-bottom: 1px solid #e2e8f0;
    padding: 1rem 1.5rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 1rem;
    flex: 1;
    min-width: 0;
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .back-btn {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.5rem 0.75rem;
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    color: #64748b;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s ease;
    outline: none !important;
  }
  
  .back-btn:focus {
    outline: none !important;
    box-shadow: none !important;
  }

  .back-btn:hover {
    background: #f1f5f9;
    border-color: #cbd5e1;
    color: #475569;
  }

  .back-btn svg {
    width: 16px;
    height: 16px;
  }

  .divider {
    width: 1px;
    height: 24px;
    background: #e2e8f0;
  }

  .job-title {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    min-width: 0;
    user-select: none;
    -webkit-user-select: none;
    -moz-user-select: none;
    -ms-user-select: none;
  }

  .job-label {
    font-size: 1rem;
    font-weight: 600;
    color: #1e293b;
  }

  .separator {
    color: #94a3b8;
    font-weight: 400;
  }

  .job-name {
    font-size: 0.875rem;
    color: #64748b;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .refresh-btn, .cancel-btn {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.5rem 1rem;
    border: none;
    border-radius: 8px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s ease;
    outline: none !important;
  }
  
  .refresh-btn:focus, .cancel-btn:focus {
    outline: none !important;
    box-shadow: none !important;
  }

  .refresh-btn {
    background: #3b82f6;
    color: white;
  }

  .refresh-btn:hover:not(:disabled) {
    background: #2563eb;
  }

  .refresh-btn:disabled {
    background: #94a3b8;
    cursor: not-allowed;
  }

  .cancel-btn {
    background: #ef4444;
    color: white;
  }

  .cancel-btn:hover:not(:disabled) {
    background: #dc2626;
  }

  .cancel-btn:disabled {
    background: #94a3b8;
    cursor: not-allowed;
  }

  .refresh-btn svg {
    width: 16px;
    height: 16px;
  }

  .spinning {
    animation: spin 1s linear infinite;
  }
  
  /* Overflow Menu */
  .overflow-menu-container {
    position: relative;
  }
  
  .overflow-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    padding: 0;
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    color: #64748b;
    cursor: pointer;
    transition: all 0.15s ease;
    outline: none !important;
  }
  
  .overflow-btn:focus {
    outline: none !important;
    box-shadow: none !important;
  }
  
  .overflow-btn:hover {
    background: #f1f5f9;
    border-color: #cbd5e1;
    color: #475569;
  }
  
  .overflow-btn svg {
    width: 20px;
    height: 20px;
  }
  
  .overflow-menu {
    position: absolute;
    top: calc(100% + 8px);
    right: 0;
    min-width: 220px;
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.1), 0 4px 10px rgba(0, 0, 0, 0.05);
    z-index: 1000;
    animation: slideDown 0.2s ease;
    overflow: hidden;
  }

  @media (max-width: 768px) {
    .overflow-menu {
      position: fixed;
      top: auto;
      bottom: 20px;
      left: 20px;
      right: 20px;
      min-width: auto;
      border-radius: 16px;
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.15);
    }

    .menu-item {
      padding: 1rem;
      font-size: 0.9rem;
      gap: 1rem;
      min-height: 56px;
      display: flex;
      align-items: center;
    }

    .menu-item svg {
      width: 20px;
      height: 20px;
    }

    .menu-label {
      padding: 0.75rem 1rem 0.5rem;
      font-size: 0.7rem;
    }
  }
  
  @keyframes slideDown {
    from {
      opacity: 0;
      transform: translateY(-10px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
  
  .menu-section {
    padding: 0.5rem 0;
  }
  
  .menu-label {
    padding: 0.5rem 1rem;
    font-size: 0.75rem;
    font-weight: 600;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  
  .menu-item {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    width: 100%;
    padding: 0.625rem 1rem;
    background: none;
    border: none;
    color: #475569;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s ease;
    text-align: left;
    outline: none !important;
  }
  
  .menu-item:focus {
    outline: none !important;
    box-shadow: none !important;
  }
  
  .menu-item:hover {
    background: #f8fafc;
    color: #1e293b;
  }
  
  .menu-item:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  
  .menu-item.danger {
    color: #dc2626;
  }
  
  .menu-item.danger:hover {
    background: #fef2f2;
    color: #b91c1c;
  }
  
  .menu-item svg {
    width: 18px;
    height: 18px;
    flex-shrink: 0;
  }
  
  .menu-divider {
    height: 1px;
    background: #e2e8f0;
    margin: 0.25rem 0;
  }

  .state-badge {
    padding: 0.375rem 0.875rem;
    border-radius: 20px;
    color: white;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.025em;
  }

  /* Error Container */
  .error-container {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 2rem;
    gap: 1rem;
  }

  .error-container svg {
    width: 48px;
    height: 48px;
    color: #ef4444;
  }

  .error-container h2 {
    margin: 0;
    font-size: 1.25rem;
    color: #1e293b;
  }

  .error-container p {
    margin: 0;
    color: #64748b;
  }

  .error-container button {
    padding: 0.5rem 1rem;
    background: #3b82f6;
    color: white;
    border: none;
    border-radius: 8px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
  }

  .error-container button:hover {
    background: #2563eb;
  }

  /* Content Controls - Clean Tab System */
  .content-controls {
    width: 100%;
    padding: 1rem 2rem;
    background: white;
    border-bottom: 1px solid #e2e8f0;
  }
  
  .view-selection {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.75rem;
  }
  
  .tabs-left {
    display: flex;
    gap: 0.25rem;
  }
  
  .tabs-right {
    display: flex;
    gap: 0.5rem;
    align-items: center;
  }
  
  .tab-action-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    padding: 0;
    border: 1px solid #e2e8f0;
    background: white;
    border-radius: 6px;
    color: #64748b;
    cursor: pointer;
    transition: all 0.15s ease;
    outline: none !important;
  }
  
  .tab-action-btn:focus {
    outline: none !important;
    box-shadow: none !important;
  }
  
  .tab-action-btn:hover {
    background: #f1f5f9;
    border-color: #cbd5e1;
    color: #3b82f6;
  }
  
  .tab-action-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  
  .tab-action-btn svg {
    width: 16px;
    height: 16px;
  }
  
  .view-tab {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.625rem 1rem;
    border: none;
    background: transparent;
    border-radius: 8px;
    color: #64748b;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s ease;
    outline: none !important;
  }
  
  .view-tab:focus {
    outline: none !important;
    box-shadow: none !important;
  }
  
  .view-tab svg {
    width: 16px;
    height: 16px;
  }
  
  .view-tab:hover {
    background: #f1f5f9;
    color: #475569;
  }
  
  .view-tab.active {
    background: #3b82f6;
    color: white;
    box-shadow: 0 1px 3px rgba(59, 130, 246, 0.2);
  }
  
  .tab-label {
    font-weight: 500;
  }

  /* Content */
  .content {
    flex: 1;
    overflow-y: auto;
    padding: 2rem;
  }

  /* Info Grid */
  .info-container {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 1rem;
  }

  .info-card {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 1.5rem;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  }
  
  .info-card:hover {
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  }

  .card-title {
    margin: 0 0 1.25rem 0;
    font-size: 0.7rem;
    font-weight: 700;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    user-select: none;
    -webkit-user-select: none;
    -moz-user-select: none;
    -ms-user-select: none;
  }
  
  .card-title::before {
    content: '';
    width: 3px;
    height: 14px;
    background: linear-gradient(135deg, #3b82f6, #8b5cf6);
    border-radius: 2px;
  }

  .info-row {
    display: grid;
    grid-template-columns: 110px 1fr;
    gap: 1rem;
    padding: 0.875rem 0.5rem;
    border-bottom: 1px solid #f8fafc;
  }

  .info-row:last-child {
    border-bottom: none;
  }

  .info-row.full-width {
    grid-column: 1 / -1;
  }

  .info-label {
    font-size: 0.85rem;
    font-weight: 600;
    color: #94a3b8;
    display: flex;
    align-items: center;
  }

  .info-value {
    font-size: 0.9rem;
    color: #0f172a;
    word-break: break-word;
    font-weight: 500;
    display: flex;
    align-items: center;
  }

  .info-value.mono {
    font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
    background: linear-gradient(135deg, #f8fafc, #f1f5f9);
    padding: 0.375rem 0.625rem;
    border-radius: 6px;
    font-size: 0.825rem;
    border: 1px solid #e2e8f0;
    font-weight: 400;
  }

  /* Output Section */
  .output-section {
    height: 100%;
    display: flex;
    flex-direction: column;
  }

  .output-content {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 1.25rem;
    margin: 0;
    font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Fira Code', monospace;
    font-size: 0.8rem;
    line-height: 1.6;
    white-space: pre-wrap;
    word-wrap: break-word;
    word-break: break-word;
    overflow-wrap: break-word;
    overflow: auto;
    flex: 1;
  }

  .output-content.error {
    background: #fef2f2;
    border-color: #fecaca;
    color: #991b1b;
  }

  .output-content.script {
    background: #f0f9ff;
    border-color: #bae6fd;
  }

  /* States */
  .loading-state,
  .empty-state,
  .error-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 3rem;
    gap: 1rem;
  }

  @media (max-width: 768px) {
    .loading-state {
      flex-direction: row;
      padding: 0.75rem 1rem;
      background: #f0f9ff;
      border: 1px solid #bfdbfe;
      border-radius: 8px;
      margin: 0.5rem;
    }
  }

  .empty-state {
    color: #94a3b8;
  }

  .empty-state svg {
    width: 48px;
    height: 48px;
    opacity: 0.3;
  }

  .error-state {
    color: #ef4444;
  }

  .spinner {
    width: 32px;
    height: 32px;
    border: 3px solid #e2e8f0;
    border-top-color: #3b82f6;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  .output-container {
    display: flex;
    flex-direction: column;
    height: 100%;
  }

  .output-container .output-content {
    flex: 1;
  }

  .loading-more {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    padding: 1rem;
    background: #f8fafc;
    border-top: 1px solid #e2e8f0;
    font-size: 0.9rem;
    color: #64748b;
  }

  .loading-more .spinner {
    width: 16px;
    height: 16px;
    border-width: 2px;
  }


  .retry-btn {
    padding: 0.375rem 0.875rem;
    background: #3b82f6;
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s ease;
  }

  .retry-btn:hover {
    background: #2563eb;
  }

  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }

  /* Mobile */
  @media (max-width: 768px) {
    .header {
      padding: 0.5rem 0.75rem;
      flex-direction: row;
      align-items: center;
      gap: 0.75rem;
      min-height: auto;
    }

    .header-left {
      gap: 0.75rem;
      overflow: hidden;
      flex: 1;
    }

    .job-title {
      gap: 0.25rem;
      flex-shrink: 1;
      min-width: 0;
      display: flex;
      flex-direction: column;
      align-items: flex-start;
    }

    .job-label {
      font-size: 0.85rem;
      line-height: 1.2;
    }

    .job-name {
      font-size: 0.75rem;
      color: #9ca3af;
      line-height: 1.2;
      max-width: none;
    }

    .separator {
      display: none; /* Hide separator on mobile */
    }

    .header-right {
      justify-content: flex-end;
      flex-shrink: 0;
      gap: 0.5rem;
    }

    .refresh-btn {
      padding: 0 !important;
      font-size: 0 !important;
      min-width: 40px;
      min-height: 40px;
      width: 40px;
      height: 40px;
      border-radius: 8px;
      display: flex !important;
      align-items: center !important;
      justify-content: center !important;
      gap: 0 !important;
    }

    .refresh-btn svg {
      margin: 0 !important;
      width: 18px;
      height: 18px;
    }

    .overflow-btn {
      width: 40px;
      height: 40px;
      border-radius: 8px;
    }

    .overflow-btn svg {
      width: 18px;
      height: 18px;
    }

    .state-badge {
      padding: 0.25rem 0.5rem;
      font-size: 0.65rem;
      border-radius: 6px;
    }

    .content-controls {
      padding: 0.75rem 1rem;
    }
    
    .view-selection {
      margin-bottom: 0.5rem;
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
    }
    
    .view-tab {
      padding: 0.5rem 0.75rem;
      font-size: 0.8rem;
      flex-shrink: 0;
      min-width: 70px;
      justify-content: center;
      gap: 0.25rem;
    }
    
    .view-tab svg {
      width: 14px;
      height: 14px;
    }
    
    .tab-label {
      display: none;
    }

    .content {
      padding: 1rem;
    }

    .info-container {
      grid-template-columns: 1fr;
      gap: 0.75rem;
    }

    .info-card {
      padding: 1rem;
    }

    .info-row {
      grid-template-columns: 1fr;
      gap: 0.25rem;
      padding: 0.5rem 0.25rem;
    }

    .info-label {
      font-size: 0.75rem;
      color: #6b7280;
    }

    .info-value {
      font-size: 0.85rem;
    }

    .card-title {
      font-size: 0.65rem;
      margin-bottom: 1rem;
    }

    /* Mobile output styling simplified since controls are now in tabs */

    .output-content {
      padding: 1rem;
      font-size: 0.75rem;
      line-height: 1.5;
      word-wrap: break-word;
      word-break: break-word;
      overflow-wrap: break-word;
      white-space: pre-wrap;
      overflow-x: auto;
      overflow-y: auto;
      max-width: 100%;
    }

    .loading-state,
    .empty-state,
    .error-state {
      padding: 1rem;
    }

    .loading-state {
      padding: 0.75rem;
      gap: 0.5rem;
    }

    .loading-state .spinner {
      width: 20px;
      height: 20px;
      border-width: 2px;
    }

    .loading-state span {
      font-size: 0.8rem;
    }

    .mobile-sidebar-btn {
      width: 44px;
      height: 44px;
    }

    .mobile-sidebar-btn svg {
      width: 18px;
      height: 18px;
    }
  }
  /* Layout with sidebar */
  .page-layout {
    display: flex;
    height: 100%;
    position: relative;
  }
  
  .job-content-area {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
  }
  
  /* Mobile sidebar overlay */
  .mobile-sidebar-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: white;
    z-index: 1000;
    display: flex;
    flex-direction: column;
  }
  
  .mobile-toggle-btn {
    position: absolute;
    bottom: 20px;
    left: 50%;
    transform: translateX(-50%);
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 1.5rem;
    background: #3b82f6;
    color: white;
    border: none;
    border-radius: 24px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
    transition: all 0.2s ease;
  }
  
  .mobile-toggle-btn:hover {
    background: #2563eb;
    transform: translateX(-50%) translateY(-2px);
    box-shadow: 0 6px 16px rgba(59, 130, 246, 0.4);
  }
  
  .mobile-toggle-btn svg {
    width: 18px;
    height: 18px;
  }
  
  .mobile-sidebar-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.15s ease;
    outline: none !important;
  }
  
  .mobile-sidebar-btn:focus {
    outline: none !important;
    box-shadow: none !important;
  }
  
  .mobile-sidebar-btn:hover {
    background: #f1f5f9;
    border-color: #cbd5e1;
  }
  
  .mobile-sidebar-btn svg {
    width: 20px;
    height: 20px;
    color: #64748b;
  }
</style>

{#if showAttachWatchersDialog && job}
  <AttachWatchersDialog 
    jobId={job.job_id}
    hostname={params.host}
    on:close={() => showAttachWatchersDialog = false}
    on:success={() => {
      showAttachWatchersDialog = false;
      // Optionally refresh job to show new watchers
      loadJob(true);
    }}
  />
{/if}