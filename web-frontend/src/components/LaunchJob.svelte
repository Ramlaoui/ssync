<script lang="ts">
  import { onDestroy } from "svelte";
  import { api } from "../services/api";
  import type { AxiosError } from "axios";
  import { onMount } from "svelte";
  import type { LaunchJobRequest, LaunchJobResponse, HostInfo } from "../types/api";
  // Import new components
  import FileBrowser from "./FileBrowser.svelte";
  import JobConfigForm from "./JobConfigForm.svelte";
  import ScriptPreview from "./ScriptPreview.svelte";
  import SyncSettings from "./SyncSettings.svelte";
  import ConfirmationDialog from "./ConfirmationDialog.svelte";
  // Import store and actions
  import {
    config,
    error,
    generatedScript,
    hosts as hostsStore,
    isValid,
    jobLaunchActions,
    launching,
    loading,
    success,
    validationDetails,
  } from "../stores/jobLaunch";

  // Accept hosts as prop
  export let hosts: HostInfo[] = [];

  // Confirmation dialog state
  let showConfirmationDialog = false;
  let confirmationMessage = "";
  let directoryStats: { file_count: number; size_mb: number; dangerous_path: boolean; gitignore_applied?: boolean } | null = null;
  let pendingLaunchRequest: LaunchJobRequest | null = null;

  // Mobile tab state
  let activeTab: 'config' | 'browser' | 'sync' | 'script' = 'config';
  let isMobile = false;

  // Check if mobile
  function checkMobile() {
    isMobile = window.innerWidth <= 768;
  }

  onMount(() => {
    checkMobile();
    window.addEventListener('resize', checkMobile);
  });

  onDestroy(() => {
    if (typeof window !== 'undefined') {
      window.removeEventListener('resize', checkMobile);
    }
  });

  onMount(async () => {
    // Use hosts prop if available, otherwise load them
    if (hosts && hosts.length > 0) {
      jobLaunchActions.setHosts(hosts);
      // Auto-select first host if none selected
      if (!$config.selectedHost) {
        jobLaunchActions.setSelectedHost(hosts[0].hostname);
        jobLaunchActions.applyHostDefaults(hosts[0].hostname);
      }
    } else {
      await loadHosts();
    }
  });

  // debug: trace $launching changes
  let _prevLaunchingVal: boolean | null = null;
  $: if ($launching !== _prevLaunchingVal) {
    _prevLaunchingVal = $launching;
    // eslint-disable-next-line no-console
    console.debug('[debug] $launching ->', $launching);
  }

  async function loadHosts(): Promise<void> {
    jobLaunchActions.setLoading(true);
    try {
      const response = await api.get('/hosts');
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

  async function launchJob(forceSync: boolean = false): Promise<void> {
    // Validate using store
    if (!$isValid) {
      jobLaunchActions.setError("Please complete all required fields");
      return;
    }

    jobLaunchActions.setLaunching(true);
    // debug
    // eslint-disable-next-line no-console
    console.debug('[debug] launchJob started, setLaunching(true)');
    jobLaunchActions.resetMessages();

    try {
      const cfg = $config;
      const scriptToSend =
        cfg.scriptSource === "local"
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
        exclude: cfg.excludePatterns,
        include: cfg.includePatterns,
        no_gitignore: cfg.noGitignore,
        force_sync: forceSync,
      };

      const response = await api.post<LaunchJobResponse>(
        '/jobs/launch',
        request,
      );

      if (response.data.success) {
        jobLaunchActions.setSuccess(
          `Job launched successfully! Job ID: ${response.data.job_id}`,
        );
        
        // Show directory warning if present
        if (response.data.directory_warning) {
          jobLaunchActions.setError(`Warning: ${response.data.directory_warning}`);
        }
        
        // Reset some fields but keep host and directory
        jobLaunchActions.updateJobConfig({
          jobName: "",
          outputFile: "",
          errorFile: "",
          gres: "",
          scriptContent:
            '#!/bin/bash\n\n# Your script here\necho "Hello, SLURM!"',
          scriptSource: "editor",
          localScriptPath: "",
          uploadedScriptName: "",
          useMemory: false,
        });
      } else {
        // Check if this requires confirmation
        if (response.data.requires_confirmation) {
          // Store the request for retry with force_sync
          pendingLaunchRequest = request;
          confirmationMessage = response.data.message;
          directoryStats = response.data.directory_stats || null;
          showConfirmationDialog = true;
          jobLaunchActions.setLaunching(false);
          return;
        }
        
        jobLaunchActions.setError(response.data.message);
      }
    } catch (err: unknown) {
      const axiosError = err as AxiosError;
      if (
        axiosError.response?.data &&
        typeof axiosError.response.data === "object" &&
        "detail" in axiosError.response.data
      ) {
        jobLaunchActions.setError(axiosError.response.data.detail as string);
      } else {
        jobLaunchActions.setError(
          `Failed to launch job: ${axiosError.message}`,
        );
      }
    } finally {
      jobLaunchActions.setLaunching(false);
  // debug
  // eslint-disable-next-line no-console
  console.debug('[debug] launchJob finished, setLaunching(false)');
    }
  }

  // Event handlers for component communication
  function handleConfigChange(event: CustomEvent) {
    jobLaunchActions.updateJobConfig(event.detail);
  }

  function handleScriptChange(event: CustomEvent) {
    // Handle different types of script changes
    // Clean the saved script: remove shebang, generated header, host/source comments and any SBATCH directives
    const raw = event.detail.content as string;
    const withoutShebang = raw.replace(/^#![^\n]*\n?/, "");
    const lines = withoutShebang.split("\n");
    const cleanedLines = lines.filter((l) => {
      const t = l.trim();
      if (!t) return true; // keep blank lines
      if (t.startsWith("#SBATCH")) return false;
      if (t.startsWith("# Generated")) return false;
      if (t.startsWith("# Host:")) return false;
      if (t.startsWith("# Source:")) return false;
      return true;
    });
    const cleaned = cleanedLines.join("\n").trim();
    jobLaunchActions.setScriptContent(cleaned);
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

  function handleConfirmForceSync() {
    showConfirmationDialog = false;
    if (pendingLaunchRequest) {
      launchJob(true); // Retry with force_sync = true
      pendingLaunchRequest = null;
      directoryStats = null;
    }
  }

  function handleCancelForceSync() {
    showConfirmationDialog = false;
    pendingLaunchRequest = null;
    directoryStats = null;
    jobLaunchActions.setLaunching(false);
  }
</script>

<div class="launch-container">
  {#if $error}
    <div class="error-message">
      <svg viewBox="0 0 24 24" fill="currentColor">
        <path
          d="M12,2C17.53,2 22,6.47 22,12C22,17.53 17.53,22 12,22C6.47,22 2,17.53 2,12C2,6.47 6.47,2 12,2M15.59,7L12,10.59L8.41,7L7,8.41L10.59,12L7,15.59L8.41,17L12,13.41L15.59,17L17,15.59L13.41,12L17,8.41L15.59,7Z"
        />
      </svg>
      {$error}
    </div>
  {/if}

  {#if $success}
    <div class="success-message">
      <svg viewBox="0 0 24 24" fill="currentColor">
        <path
          d="M12,2C17.53,2 22,6.47 22,12C22,17.53 17.53,22 12,22C6.47,22 2,17.53 2,12C2,6.47 6.47,2 12,2M17,9L12,14L7,9L8.41,7.59L12,11.17L15.59,7.59L17,9Z"
        />
      </svg>
      {$success}
    </div>
  {/if}

  {#if isMobile}
    <!-- Mobile Tab Navigation -->
    <nav class="mobile-tabs">
      <button 
        class="tab-button" 
        class:active={activeTab === 'config'}
        on:click={() => activeTab = 'config'}
      >
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M12,15.5A3.5,3.5 0 0,1 8.5,12A3.5,3.5 0 0,1 12,8.5A3.5,3.5 0 0,1 15.5,12A3.5,3.5 0 0,1 12,15.5M19.43,12.97C19.47,12.65 19.5,12.33 19.5,12C19.5,11.67 19.47,11.34 19.43,11L21.54,9.37C21.73,9.22 21.78,8.95 21.66,8.73L19.66,5.27C19.54,5.05 19.27,4.96 19.05,5.05L16.56,6.05C16.04,5.66 15.5,5.32 14.87,5.07L14.5,2.42C14.46,2.18 14.25,2 14,2H10C9.75,2 9.54,2.18 9.5,2.42L9.13,5.07C8.5,5.32 7.96,5.66 7.44,6.05L4.95,5.05C4.73,4.96 4.46,5.05 4.34,5.27L2.34,8.73C2.21,8.95 2.27,9.22 2.46,9.37L4.57,11C4.53,11.34 4.5,11.67 4.5,12C4.5,12.33 4.53,12.65 4.57,12.97L2.46,14.63C2.27,14.78 2.21,15.05 2.34,15.27L4.34,18.73C4.46,18.95 4.73,19.03 4.95,18.95L7.44,17.94C7.96,18.34 8.5,18.68 9.13,18.93L9.5,21.58C9.54,21.82 9.75,22 10,22H14C14.25,22 14.46,21.82 14.5,21.58L14.87,18.93C15.5,18.67 16.04,18.34 16.56,17.94L19.05,18.95C19.27,19.03 19.54,18.95 19.66,18.73L21.66,15.27C21.78,15.05 21.73,14.78 21.54,14.63L19.43,12.97Z"/>
        </svg>
        Config
      </button>
      <button 
        class="tab-button" 
        class:active={activeTab === 'browser'}
        on:click={() => activeTab = 'browser'}
      >
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M10,4H4C2.89,4 2,4.89 2,6V18A2,2 0 0,0 4,20H20A2,2 0 0,0 22,18V8C22,6.89 21.1,6 20,6H12L10,4Z"/>
        </svg>
        Directory
      </button>
      <button 
        class="tab-button" 
        class:active={activeTab === 'sync'}
        on:click={() => activeTab = 'sync'}
      >
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M12,18A6,6 0 0,1 6,12C6,11 6.25,10.03 6.7,9.2L5.24,7.74C4.46,8.97 4,10.43 4,12A8,8 0 0,0 12,20V23L16,19L12,15M12,4V1L8,5L12,9V6A6,6 0 0,1 18,12C18,13 17.75,13.97 17.3,14.8L18.76,16.26C19.54,15.03 20,13.57 20,12A8,8 0 0,0 12,4Z"/>
        </svg>
        Sync
      </button>
      <button 
        class="tab-button" 
        class:active={activeTab === 'script'}
        on:click={() => activeTab = 'script'}
      >
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M14.6,16.6L19.2,12L14.6,7.4L16,6L22,12L16,18L14.6,16.6M9.4,16.6L4.8,12L9.4,7.4L8,6L2,12L8,18L9.4,16.6Z"/>
        </svg>
        Script
      </button>
    </nav>
  {/if}

  <div class="main-layout" class:mobile-layout={isMobile}>
    {#if !isMobile}
      <!-- Desktop Layout: Side by side -->
      <div class="config-panel">
        <div class="config-content">
          <!-- Job Configuration Form -->
        <JobConfigForm
          hosts={$hostsStore}
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
          loading={$loading}
          on:configChanged={handleConfigChange}
        />

        <!-- Source Directory Browser -->
        <div class="browser-section">
          <h3>Directory Browser</h3>
          <FileBrowser
            sourceDir={$config.sourceDir}
            initialPath={"/home"}
            on:pathSelected={handlePathSelected}
            on:change={(e) => jobLaunchActions.setSourceDir(e.detail)}
          />
        </div>

        <!-- Sync Settings -->
        <div class="sync-settings-wrapper">
          <SyncSettings
            excludePatterns={$config.excludePatterns}
            includePatterns={$config.includePatterns}
            noGitignore={$config.noGitignore}
            on:settingsChanged={handleSyncSettingsChange}
          />
        </div>
      </div>
    </div>

    <!-- Right Column: Script Editor Only -->
    <div class="right-column">
      <!-- Script Preview -->
      <ScriptPreview
        generatedScript={$generatedScript}
        selectedHost={$config.selectedHost}
        sourceDir={$config.sourceDir}
        launching={$launching}
        loading={$loading}
        validationDetails={$validationDetails}
        on:launch={handleLaunchJob}
        on:scriptChanged={handleScriptChange}
      />
    </div>
    {:else}
      <!-- Mobile Layout: Tabbed interface -->
      <div class="mobile-content">
        {#if activeTab === 'config'}
          <div class="mobile-tab-content">
            <JobConfigForm
              hosts={$hostsStore}
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
              loading={$loading}
              on:configChanged={handleConfigChange}
            />
          </div>
        {:else if activeTab === 'browser'}
          <div class="mobile-tab-content">
            <div class="browser-section mobile">
              <h3>Select Source Directory</h3>
              <FileBrowser
                sourceDir={$config.sourceDir}
                initialPath="/home"
                on:pathSelected={handlePathSelected}
                on:change={(e) => jobLaunchActions.setSourceDir(e.detail)}
              />
            </div>
          </div>
        {:else if activeTab === 'sync'}
          <div class="mobile-tab-content">
            <div class="sync-settings-wrapper mobile">
              <SyncSettings
                excludePatterns={$config.excludePatterns}
                includePatterns={$config.includePatterns}
                noGitignore={$config.noGitignore}
                on:settingsChanged={handleSyncSettingsChange}
              />
            </div>
          </div>
        {:else if activeTab === 'script'}
          <div class="mobile-tab-content script-tab">
            <ScriptPreview
              generatedScript={$generatedScript}
              selectedHost={$config.selectedHost}
              sourceDir={$config.sourceDir}
              launching={$launching}
              loading={$loading}
              validationDetails={$validationDetails}
              on:launch={handleLaunchJob}
              on:scriptChanged={handleScriptChange}
            />
          </div>
        {/if}
      </div>
    {/if}
  </div>
</div>

<!-- Large Directory Confirmation Dialog -->
<ConfirmationDialog
  bind:show={showConfirmationDialog}
  title="Large Directory Detected"
  message={confirmationMessage}
  confirmText="Force Sync"
  cancelText="Cancel"
  confirmButtonClass="primary"
  stats={directoryStats}
  on:confirm={handleConfirmForceSync}
  on:cancel={handleCancelForceSync}
/>

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

  .error-message,
  .success-message {
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

  .error-message svg,
  .success-message svg {
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
    content: "";
    width: 4px;
    height: 20px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 2px;
  }

  .sync-settings-wrapper {
    display: block;
    width: 100%;
  }

  .right-column {
    flex: 1.2;
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
    height: 100%;
  }

  /* Webkit scrollbar styling */
  .config-content::-webkit-scrollbar {
    width: 8px;
  }

  .config-content::-webkit-scrollbar-track {
    background: transparent;
  }

  .config-content::-webkit-scrollbar-thumb {
    background: rgba(156, 163, 175, 0.5);
    border-radius: 4px;
  }

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
      flex: 0 0 auto;
      max-height: 40vh;
      min-height: 300px;
    }

    .right-column {
      flex: 1;
      min-height: 400px;
    }
  }

  /* Mobile Tab Navigation Styles */
  .mobile-tabs {
    display: flex;
    background: white;
    border-bottom: 1px solid #e1e5e9;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
    position: sticky;
    top: 0;
    z-index: 100;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }

  .tab-button {
    flex: 1;
    min-width: 80px;
    padding: 0.75rem 0.5rem;
    background: none;
    border: none;
    border-bottom: 3px solid transparent;
    color: #6b7280;
    font-size: 0.75rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.25rem;
    white-space: nowrap;
  }

  .tab-button svg {
    width: 20px;
    height: 20px;
  }

  .tab-button:hover {
    background: #f9fafb;
  }

  .tab-button.active {
    color: #6366f1;
    border-bottom-color: #6366f1;
    background: #eef2ff;
  }

  .mobile-content {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    min-height: 0;
  }

  .mobile-tab-content {
    flex: 1;
    overflow-y: auto;
    overflow-x: hidden;
    -webkit-overflow-scrolling: touch;
    padding: 1rem;
  }

  .mobile-tab-content.script-tab {
    padding: 0;
    display: flex;
    flex-direction: column;
  }

  .browser-section.mobile,
  .sync-settings-wrapper.mobile {
    background: white;
    border-radius: 12px;
    padding: 1rem;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  }

  .browser-section.mobile h3 {
    margin: 0 0 1rem 0;
    font-size: 1.1rem;
    color: #374151;
  }

  /* Mobile Layout */
  @media (max-width: 768px) {
    .launch-container {
      height: 100vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      background: #f8fafc;
    }

    .main-layout {
      flex: 1;
      display: flex;
      flex-direction: column;
      padding: 0;
      gap: 0;
      overflow: hidden;
      min-height: 0;
    }

    .main-layout.mobile-layout {
      padding: 0;
    }

    .error-message,
    .success-message {
      margin: 0.5rem;
      padding: 0.75rem;
      font-size: 0.85rem;
      border-radius: 8px;
    }

    .error-message svg,
    .success-message svg {
      width: 1rem;
      height: 1rem;
    }

    /* Hide desktop-only elements on mobile */
    .config-panel,
    .right-column {
      display: none;
    }
  }

  /* Small Mobile Adjustments */
  @media (max-width: 480px) {
    .tab-button {
      font-size: 0.7rem;
      padding: 0.625rem 0.375rem;
    }

    .tab-button svg {
      width: 18px;
      height: 18px;
    }

    .mobile-tab-content {
      padding: 0.75rem;
    }

    .browser-section.mobile,
    .sync-settings-wrapper.mobile {
      padding: 0.875rem;
    }
  }
</style>
