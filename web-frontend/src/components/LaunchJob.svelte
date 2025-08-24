<script lang="ts">
  import { onMount } from 'svelte';
  import axios, { type AxiosError } from 'axios';
  import type { LaunchJobRequest, LaunchJobResponse } from '../types/api';
  
  // Import new components
  import JobConfigForm from './JobConfigForm.svelte';
  import ScriptPreview from './ScriptPreview.svelte';
  import SyncSettings from './SyncSettings.svelte';
  import FileBrowser from './FileBrowser.svelte';
  
  // Import store and actions
  import { 
    config, 
    hosts, 
    loading, 
    launching, 
    error, 
    success,
    generatedScript,
    isValid,
    jobLaunchActions
  } from '../stores/jobLaunch';

  const API_BASE = '/api';

  onMount(async () => {
    await loadHosts();
  });

  async function loadHosts(): Promise<void> {
    jobLaunchActions.setLoading(true);
    try {
      const response = await axios.get(`${API_BASE}/hosts`);
      jobLaunchActions.setHosts(response.data);
      
      // Auto-select first host if none selected
      if (response.data.length > 0 && !$config.selectedHost) {
        jobLaunchActions.setSelectedHost(response.data[0].hostname);
        jobLaunchActions.applyHostDefaults(response.data[0].hostname);
      }
    } catch (err: unknown) {
      const axiosError = err as AxiosError;
      jobLaunchActions.setError(`Failed to load hosts: ${axiosError.message}`);
    } finally {
      jobLaunchActions.setLoading(false);
    }
  }

  async function launchJob(): Promise<void> {
    // Validate using store
    if (!$isValid) {
      jobLaunchActions.setError('Please complete all required fields');
      return;
    }

    jobLaunchActions.setLaunching(true);
    jobLaunchActions.resetMessages();

    try {
      const cfg = $config;
      const scriptToSend = cfg.scriptSource === 'local' 
        ? `{{LOCAL:${cfg.localScriptPath}}}` 
        : cfg.scriptContent;

      const request: LaunchJobRequest = {
        script_content: scriptToSend,
        source_dir: cfg.sourceDir,
        host: cfg.selectedHost,
        job_name: cfg.jobName || undefined,
        cpus: cfg.cpus || undefined,
        mem: cfg.useMemory ? cfg.memory : undefined,
        time: cfg.timeLimit || undefined,
        partition: cfg.partition || undefined,
        ntasks_per_node: cfg.ntasksPerNode || undefined,
        n_tasks_per_node: cfg.ntasksPerNode || undefined,
        nodes: cfg.nodes || undefined,
        gpus_per_node: cfg.gpusPerNode || undefined,
        gres: cfg.gres || undefined,
        output: cfg.outputFile || undefined,
        error: cfg.errorFile || undefined,
        constraint: cfg.constraint || undefined,
        account: cfg.account || undefined,
        python_env: cfg.pythonEnv || undefined,
        exclude: cfg.excludePatterns,
        include: cfg.includePatterns,
        no_gitignore: cfg.noGitignore
      };

      const response = await axios.post<LaunchJobResponse>(`${API_BASE}/jobs/launch`, request);
      
      if (response.data.success) {
        jobLaunchActions.setSuccess(`Job launched successfully! Job ID: ${response.data.job_id}`);
        // Reset some fields but keep host and directory
        jobLaunchActions.updateJobConfig({
          jobName: '',
          outputFile: '',
          errorFile: '',
          gres: '',
          pythonEnv: '',
          scriptContent: '#!/bin/bash\n\n# Your script here\necho "Hello, SLURM!"',
          scriptSource: 'editor',
          localScriptPath: '',
          uploadedScriptName: '',
          useMemory: false
        });
      } else {
        jobLaunchActions.setError(response.data.message);
      }
    } catch (err: unknown) {
      const axiosError = err as AxiosError;
      if (axiosError.response?.data && typeof axiosError.response.data === 'object' && 'detail' in axiosError.response.data) {
        jobLaunchActions.setError(axiosError.response.data.detail as string);
      } else {
        jobLaunchActions.setError(`Failed to launch job: ${axiosError.message}`);
      }
    } finally {
      jobLaunchActions.setLaunching(false);
    }
  }

  // Event handlers for component communication
  function handleConfigChange(event: CustomEvent) {
    jobLaunchActions.updateJobConfig(event.detail);
    // Apply host defaults when host changes
    if (event.detail.selectedHost && event.detail.selectedHost !== $config.selectedHost) {
      jobLaunchActions.applyHostDefaults(event.detail.selectedHost);
    }
  }

  function handleScriptChange(event: CustomEvent) {
    // Handle different types of script changes
    if (event.detail.content && typeof event.detail.content === 'string') {
      // Direct content change from editable preview
      jobLaunchActions.setScriptContent(event.detail.content);
    } else {
      // Script config change from editor component
      jobLaunchActions.setScriptConfig(event.detail);
    }
  }

  function handleSyncSettingsChange(event: CustomEvent) {
    jobLaunchActions.setSyncSettings(event.detail);
  }

  function handlePathSelected(event: CustomEvent) {
    jobLaunchActions.setSourceDir(event.detail);
  }


  function handleLaunchJob() {
    launchJob();
  }
</script>

<div class="launch-container">
  {#if $error}
    <div class="error-message">
      <svg viewBox="0 0 24 24" fill="currentColor">
        <path d="M12,2C17.53,2 22,6.47 22,12C22,17.53 17.53,22 12,22C6.47,22 2,17.53 2,12C2,6.47 6.47,2 12,2M15.59,7L12,10.59L8.41,7L7,8.41L10.59,12L7,15.59L8.41,17L12,13.41L15.59,17L17,15.59L13.41,12L17,8.41L15.59,7Z"/>
      </svg>
      {$error}
    </div>
  {/if}

  {#if $success}
    <div class="success-message">
      <svg viewBox="0 0 24 24" fill="currentColor">
        <path d="M12,2C17.53,2 22,6.47 22,12C22,17.53 17.53,22 12,22C6.47,22 2,17.53 2,12C2,6.47 6.47,2 12,2M17,9L12,14L7,9L8.41,7.59L12,11.17L15.59,7.59L17,9Z"/>
      </svg>
      {$success}
    </div>
  {/if}

  <div class="main-layout">
    <!-- Left Panel: Configuration Forms -->
    <div class="config-panel">
      <div class="config-content">
        <!-- Job Configuration Form -->
        <JobConfigForm 
          hosts={$hosts}
          selectedHost={$config.selectedHost}
          sourceDir={$config.sourceDir}
          jobName={$config.jobName}
          partition={$config.partition}
          constraint={$config.constraint}
          account={$config.account}
          cpus={$config.cpus}
          useMemory={$config.useMemory}
          memory={$config.memory}
          timeLimit={$config.timeLimit}
          nodes={$config.nodes}
          ntasksPerNode={$config.ntasksPerNode}
          gpusPerNode={$config.gpusPerNode}
          gres={$config.gres}
          outputFile={$config.outputFile}
          errorFile={$config.errorFile}
          pythonEnv={$config.pythonEnv}
          loading={$loading}
          on:configChanged={handleConfigChange}
        />
        
        <!-- Source Directory Browser -->
        <div class="browser-section">
          <h3>Directory Browser</h3>
          <FileBrowser 
            bind:sourceDir={$config.sourceDir}
            on:pathSelected={handlePathSelected}
          />
        </div>
        
      </div>
    </div>
    
    <!-- Right Column: Script Preview + Sync Settings -->
    <div class="right-column">
      <div class="right-scroll-container">
        <!-- Script Preview -->
        <ScriptPreview 
          generatedScript={$generatedScript}
          selectedHost={$config.selectedHost}
          sourceDir={$config.sourceDir}
          launching={$launching}
          loading={$loading}
          on:launch={handleLaunchJob}
          on:scriptChanged={handleScriptChange}
        />
        
        <!-- Sync Settings -->
        <SyncSettings 
          excludePatterns={$config.excludePatterns}
          includePatterns={$config.includePatterns}
          noGitignore={$config.noGitignore}
          on:settingsChanged={handleSyncSettingsChange}
        />
      </div>
    </div>
  </div>
</div>

<style>
  .launch-container {
    width: 100%;
    height: 100vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  }

  .main-layout {
    flex: 1;
    display: flex;
    padding: 1.5rem;
    gap: 1.5rem;
    min-height: 0;
    overflow: hidden;
  }

  .error-message, .success-message {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 1rem 1.25rem;
    border-radius: 10px;
    margin: 1.5rem 1.5rem 0;
    font-size: 0.9rem;
    font-weight: 500;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    backdrop-filter: blur(10px);
  }

  .error-message {
    background: linear-gradient(135deg, #fef2f2 0%, #fde8e8 100%);
    color: #dc2626;
    border: 1px solid #fecaca;
  }

  .success-message {
    background: linear-gradient(135deg, #f0fdf4 0%, #e8f5e8 100%);
    color: #16a34a;
    border: 1px solid #bbf7d0;
  }

  .error-message svg, .success-message svg {
    width: 1.2rem;
    height: 1.2rem;
    flex-shrink: 0;
  }

  .config-panel {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
  }

  .config-content {
    flex: 1;
    overflow-y: auto;
    overflow-x: hidden;
    min-height: 0;
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
    padding-right: 0.5rem;
  }

  .browser-section {
    background: #fafbfc;
    border: 1px solid #e1e5e9;
    border-radius: 10px;
    padding: 1.25rem;
    transition: all 0.2s ease;
  }

  .browser-section:hover {
    border-color: #c7d2fe;
    box-shadow: 0 2px 8px rgba(99, 102, 241, 0.1);
  }

  .browser-section h3 {
    margin: 0 0 1rem 0;
    color: #374151;
    font-size: 1.125rem;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .browser-section h3::before {
    content: '';
    width: 4px;
    height: 20px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 2px;
  }

  .right-column {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
    height: 100%;
  }

  .right-scroll-container {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 1rem;
    overflow-y: auto;
    overflow-x: hidden;
    padding: 0.25rem 0.5rem 0.25rem 0;
    min-height: 0;
    scrollbar-width: thin;
    scrollbar-color: rgba(156, 163, 175, 0.5) transparent;
  }

  /* Webkit scrollbar styling */
  .right-scroll-container::-webkit-scrollbar,
  .config-content::-webkit-scrollbar {
    width: 8px;
  }

  .right-scroll-container::-webkit-scrollbar-track,
  .config-content::-webkit-scrollbar-track {
    background: transparent;
  }

  .right-scroll-container::-webkit-scrollbar-thumb,
  .config-content::-webkit-scrollbar-thumb {
    background: rgba(156, 163, 175, 0.5);
    border-radius: 4px;
  }

  .right-scroll-container::-webkit-scrollbar-thumb:hover,
  .config-content::-webkit-scrollbar-thumb:hover {
    background: rgba(156, 163, 175, 0.7);
  }

  /* Mobile responsive */
  @media (max-width: 1200px) {
    .main-layout {
      flex-direction: column;
      gap: 1rem;
      height: calc(100vh - 3rem);
    }

    .config-panel {
      flex: 1;
      max-height: 55vh;
      min-height: 400px;
    }

    .right-column {
      flex: 1;
      max-height: 40vh;
      min-height: 300px;
    }

    .right-scroll-container {
      flex-direction: row;
      gap: 1rem;
      height: 100%;
    }
  }

  @media (max-width: 768px) {
    .launch-container {
      height: 100vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }

    .main-layout {
      padding: 0.75rem;
      padding-bottom: 2rem;
      gap: 0.75rem;
      flex-direction: column;
      flex: 1;
      overflow-y: auto;
      overflow-x: hidden;
      -webkit-overflow-scrolling: touch;
      min-height: 0;
    }

    .config-panel {
      display: contents;
    }

    .config-content {
      display: contents;
    }

    .right-column {
      flex-shrink: 0;
      width: 100%;
      height: auto;
      min-height: auto;
      margin-top: 0;
      display: contents;
    }

    .right-scroll-container {
      display: contents;
    }

    .error-message, .success-message {
      margin: 0 0 1rem 0;
      padding: 0.875rem 1rem;
      font-size: 0.85rem;
    }

    .browser-section {
      background: white;
      border-radius: 12px;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
      padding: 1rem;
      margin-bottom: 1rem;
    }
  }
</style>