<script lang="ts">
  import { onMount, createEventDispatcher } from 'svelte';
  import { api } from '../services/api';
  import type { AxiosError } from 'axios';
  import { jobLaunchStore } from '../stores/jobLaunch';
  import JobConfigForm from './JobConfigForm.svelte';
  import ScriptPreview from './ScriptPreview.svelte';
  import SyncSettings from './SyncSettings.svelte';
  import FileBrowser from './FileBrowser.svelte';
  import type { HostInfo, LaunchJobRequest, LaunchJobResponse } from '../types/api';

  export let hosts: HostInfo[] = [];

  const dispatch = createEventDispatcher();
  const { state, updateConfig, reset } = jobLaunchStore;

  let currentStep: 'config' | 'script' | 'sync' | 'review' = 'config';
  let isLaunching = false;
  let launchError: string | null = null;
  let launchSuccess: string | null = null;
  let showFileBrowser = false;

  onMount(async () => {
    // Load hosts if not provided
    if (hosts.length === 0) {
      try {
        const response = await api.get<HostInfo[]>('/hosts');
        hosts = response.data;
        $state.hosts = hosts;
      } catch (err) {
        const axiosError = err as AxiosError;
        if (axiosError.response?.status === 401) {
          launchError = 'Authentication failed. Please check your API key.';
        } else {
          launchError = `Failed to load hosts: ${axiosError.message}`;
        }
      }
    } else {
      $state.hosts = hosts;
    }
  });

  function handleConfigUpdate(field: string, value: any) {
    updateConfig({ [field]: value });
  }

  function nextStep() {
    if (currentStep === 'config') {
      currentStep = 'script';
    } else if (currentStep === 'script') {
      currentStep = 'sync';
    } else if (currentStep === 'sync') {
      currentStep = 'review';
    }
  }

  function prevStep() {
    if (currentStep === 'review') {
      currentStep = 'sync';
    } else if (currentStep === 'sync') {
      currentStep = 'script';
    } else if (currentStep === 'script') {
      currentStep = 'config';
    }
  }

  function toggleFileBrowser() {
    showFileBrowser = !showFileBrowser;
  }

  function handleDirectorySelect(event: CustomEvent<string>) {
    updateConfig({ sourceDir: event.detail });
    showFileBrowser = false;
  }

  async function launchJob() {
    isLaunching = true;
    launchError = null;
    launchSuccess = null;

    // Get selected host defaults
    const selectedHost = hosts.find(h => h.hostname === $state.config.selectedHost);
    const defaults = selectedHost?.slurm_defaults;

    // Build request
    const request: LaunchJobRequest = {
      host: $state.config.selectedHost,
      source_dir: $state.config.sourceDir || undefined,
      script_content: $state.config.scriptContent,
      job_name: $state.config.jobName || defaults?.job_name_prefix || 'ssync-job',
      partition: $state.config.partition || defaults?.partition,
      constraint: $state.config.constraint || defaults?.constraint,
      account: $state.config.account || defaults?.account,
      cpus: $state.config.cpus || defaults?.cpus,
      mem: $state.config.useMemory ? ($state.config.memory || defaults?.mem) : undefined,
      time: $state.config.timeLimit || (defaults?.time ? parseInt(defaults.time) : 60),
      nodes: $state.config.nodes || defaults?.nodes,
      n_tasks_per_node: $state.config.ntasksPerNode || defaults?.ntasks_per_node,
      gpus_per_node: $state.config.gpusPerNode || defaults?.gpus_per_node,
      gres: $state.config.gres || defaults?.gres,
      output: $state.config.outputFile || defaults?.output_pattern,
      error: $state.config.errorFile || defaults?.error_pattern,
      python_env: defaults?.python_env,
      exclude: $state.config.excludePatterns.filter(p => p.trim()),
      include: $state.config.includePatterns.filter(p => p.trim()),
      no_gitignore: $state.config.noGitignore,
    };

    try {
      const response = await api.post<LaunchJobResponse>(
        '/jobs/launch',
        request
      );

      if (response.data.success) {
        launchSuccess = `Job launched successfully! Job ID: ${response.data.job_id}`;
        
        // Reset form after successful launch
        setTimeout(() => {
          reset();
          currentStep = 'config';
          dispatch('launched');
        }, 2000);
      } else {
        launchError = response.data.message || 'Failed to launch job';
      }
    } catch (err) {
      const axiosError = err as AxiosError;
      if (axiosError.response?.status === 401) {
        launchError = 'Authentication failed. Please check your API key.';
      } else if (axiosError.response?.data) {
        const errorData = axiosError.response.data as any;
        launchError = errorData.detail || errorData.message || 'Failed to launch job';
      } else {
        launchError = axiosError.message;
      }
    } finally {
      isLaunching = false;
    }
  }

  // Validation
  $: isConfigValid = $state.config.selectedHost !== '';
  $: isScriptValid = $state.config.scriptContent.trim() !== '';
  $: canLaunch = isConfigValid && isScriptValid;
</script>

<div class="launch-job">
  <div class="steps">
    <button 
      class="step" 
      class:active={currentStep === 'config'}
      on:click={() => currentStep = 'config'}
    >
      1. Configuration
    </button>
    <button 
      class="step" 
      class:active={currentStep === 'script'}
      class:disabled={!isConfigValid}
      on:click={() => isConfigValid && (currentStep = 'script')}
    >
      2. Script
    </button>
    <button 
      class="step" 
      class:active={currentStep === 'sync'}
      class:disabled={!isScriptValid}
      on:click={() => isScriptValid && (currentStep = 'sync')}
    >
      3. Sync Settings
    </button>
    <button 
      class="step" 
      class:active={currentStep === 'review'}
      class:disabled={!canLaunch}
      on:click={() => canLaunch && (currentStep = 'review')}
    >
      4. Review & Launch
    </button>
  </div>

  <div class="step-content">
    {#if launchError}
      <div class="error">{launchError}</div>
    {/if}

    {#if launchSuccess}
      <div class="success">{launchSuccess}</div>
    {/if}

    {#if currentStep === 'config'}
      <JobConfigForm 
        config={$state.config}
        hosts={$state.hosts}
        on:update={(e) => handleConfigUpdate(e.detail.field, e.detail.value)}
        on:browse={toggleFileBrowser}
      />
    {:else if currentStep === 'script'}
      <ScriptPreview 
        content={$state.config.scriptContent}
        on:update={(e) => updateConfig({ scriptContent: e.detail })}
      />
    {:else if currentStep === 'sync'}
      <SyncSettings 
        config={$state.config}
        on:update={(e) => handleConfigUpdate(e.detail.field, e.detail.value)}
      />
    {:else if currentStep === 'review'}
      <div class="review">
        <h3>Review Job Configuration</h3>
        
        <div class="review-section">
          <h4>Target</h4>
          <p><strong>Host:</strong> {$state.config.selectedHost}</p>
          {#if $state.config.sourceDir}
            <p><strong>Source Directory:</strong> {$state.config.sourceDir}</p>
          {/if}
        </div>

        <div class="review-section">
          <h4>Job Settings</h4>
          <p><strong>Job Name:</strong> {$state.config.jobName || 'default'}</p>
          {#if $state.config.partition}
            <p><strong>Partition:</strong> {$state.config.partition}</p>
          {/if}
          <p><strong>CPUs:</strong> {$state.config.cpus}</p>
          {#if $state.config.useMemory}
            <p><strong>Memory:</strong> {$state.config.memory} GB</p>
          {/if}
          <p><strong>Time Limit:</strong> {$state.config.timeLimit} minutes</p>
        </div>

        <div class="review-section">
          <h4>Script Preview</h4>
          <pre class="script-preview">{$state.config.scriptContent.substring(0, 500)}{$state.config.scriptContent.length > 500 ? '...' : ''}</pre>
        </div>
      </div>
    {/if}
  </div>

  <div class="actions">
    {#if currentStep !== 'config'}
      <button class="secondary" on:click={prevStep}>
        Previous
      </button>
    {/if}

    {#if currentStep !== 'review'}
      <button 
        class="primary" 
        on:click={nextStep}
        disabled={
          (currentStep === 'config' && !isConfigValid) ||
          (currentStep === 'script' && !isScriptValid)
        }
      >
        Next
      </button>
    {:else}
      <button 
        class="primary launch" 
        on:click={launchJob}
        disabled={!canLaunch || isLaunching}
      >
        {isLaunching ? 'Launching...' : '🚀 Launch Job'}
      </button>
    {/if}
  </div>

  {#if showFileBrowser}
    <FileBrowser 
      initialPath={$state.config.sourceDir || '/'}
      on:select={handleDirectorySelect}
      on:close={toggleFileBrowser}
    />
  {/if}
</div>

<style>
  /* ... styles remain the same ... */
</style>