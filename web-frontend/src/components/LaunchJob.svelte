<script lang="ts">
  import { onMount } from 'svelte';
  import axios, { type AxiosError } from 'axios';
  import type { HostInfo, LaunchJobRequest, LaunchJobResponse } from '../types/api';

  // Hosts / loading state
  let hosts: HostInfo[] = [];
  let loading = false;
  let launching = false;
  let error: string | null = null;
  let success: string | null = null;

  // Form data
  let selectedHost = '';
  // sourceDir can be entered manually or chosen via directory picker (webkitdirectory)
  let sourceDir = '';
  // Local filesystem browser state (server-side browsing)
  let localEntries: { name: string; path: string; is_dir: boolean }[] = [];
  let currentLocalPath = '/';
  let maxEntries = 50;
  let showHiddenFiles = false;
  let showFilesInBrowser = false;

  // Generate live script preview - trigger on all relevant variables
  $: generatedScript = generateSlurmScript(
    selectedHost, sourceDir, jobName, partition, constraint, account,
    cpus, useMemory, memory, timeLimit, nodes, ntasksPerNode, 
    gpusPerNode, gres, outputFile, errorFile, pythonEnv,
    scriptSource, scriptContent, localScriptPath, uploadedScriptName
  );

  // Script source: 'editor' | 'local' (file path relative to sourceDir) | 'upload'
  let scriptSource: 'editor' | 'local' | 'upload' = 'editor';
  let scriptContent = 'echo "Hello, SLURM!"';
  let localScriptPath = '';
  let uploadedScriptName = '';

  let jobName = '';
  let cpus = 1;
  let useMemory = false; // make memory optional
  let memory = 4; // GB default when enabled
  let timeLimit = 60; // minutes
  let partition = '';
  let ntasksPerNode = 1;
  let nodes = 1;
  let gpusPerNode = 0;
  let gres = '';
  let outputFile = '';
  let errorFile = '';
  let constraint = '';
  let account = '';
  let pythonEnv = '';
  let excludePatterns = ['*.log', '*.tmp', '__pycache__/'];
  let includePatterns: string[] = [];
  let noGitignore = false;

  // UI state
  let currentExcludePattern = '';
  let currentIncludePattern = '';

  const API_BASE = '/api';

  onMount(async () => {
    await loadHosts();
    // Load directory browser in background, don't block UI
    setTimeout(() => {
      loadLocalPath('/home').catch(() => {
        // Fallback to root if /home doesn't exist
        loadLocalPath('/').catch(() => {
          console.warn('Could not load directory browser');
        });
      });
    }, 100);
  });

  async function loadHosts(): Promise<void> {
    loading = true;
    try {
      const response = await axios.get<HostInfo[]>(`${API_BASE}/hosts`);
      hosts = response.data;
      if (hosts.length > 0 && !selectedHost) {
        selectedHost = hosts[0].hostname;
      }
    } catch (err: unknown) {
      const axiosError = err as AxiosError;
      error = `Failed to load hosts: ${axiosError.message}`;
    } finally {
      loading = false;
    }
  }

  // Handle selecting a directory via <input webkitdirectory>
  function handleDirectoryPick(e: Event): void {
    const input = e.target as HTMLInputElement;
    if (!input.files || input.files.length === 0) return;
    // webkitRelativePath gives a relative path; use the first file's root folder
    const first = input.files[0] as File & { webkitRelativePath?: string };
    const rel = first.webkitRelativePath || first.name;
    const root = rel.includes('/') ? rel.split('/')[0] : rel;
    // set sourceDir to the selected folder name (best-effort in browser)
    sourceDir = root;
  }

  // Handle uploaded script file
  function handleScriptUpload(e: Event): void {
    const input = e.target as HTMLInputElement;
    if (!input.files || input.files.length === 0) return;
    const file = input.files[0];
    uploadedScriptName = file.name;
    const reader = new FileReader();
    reader.onload = () => {
      scriptContent = String(reader.result || '');
      scriptSource = 'upload';
    };
    reader.readAsText(file);
  }

  function addExcludePattern(): void {
    if (currentExcludePattern.trim() && !excludePatterns.includes(currentExcludePattern.trim())) {
      excludePatterns = [...excludePatterns, currentExcludePattern.trim()];
      currentExcludePattern = '';
    }
  }

  function removeExcludePattern(index: number): void {
    excludePatterns = excludePatterns.filter((_, i) => i !== index);
  }

  function addIncludePattern(): void {
    if (currentIncludePattern.trim() && !includePatterns.includes(currentIncludePattern.trim())) {
      includePatterns = [...includePatterns, currentIncludePattern.trim()];
      currentIncludePattern = '';
    }
  }

  function removeIncludePattern(index: number): void {
    includePatterns = includePatterns.filter((_, i) => i !== index);
  }

  function formatMemoryLabel(value: number): string {
    if (value >= 1024) {
      return `${(value / 1024).toFixed(1)}TB`;
    }
    return `${value}GB`;
  }

  function formatTimeLabel(minutes: number): string {
    if (minutes >= 1440) {
      return `${(minutes / 1440).toFixed(1)}d`;
    } else if (minutes >= 60) {
      return `${(minutes / 60).toFixed(1)}h`;
    }
    return `${minutes}m`;
  }

  async function launchJob(): Promise<void> {
    // Validate required fields depending on script source
    if (!selectedHost || !sourceDir) {
      error = 'Please select a host and a source directory';
      return;
    }

    if (scriptSource === 'editor' && !scriptContent.trim()) {
      error = 'Script content is empty';
      return;
    }
    if (scriptSource === 'local' && !localScriptPath.trim()) {
      error = 'Please provide the local script path relative to the source directory';
      return;
    }

    launching = true;
    error = null;
    success = null;

    try {
      const scriptToSend = scriptSource === 'local' ? `{{LOCAL:${localScriptPath}}}` : scriptContent;

      const request: LaunchJobRequest = {
        script_content: scriptToSend,
        source_dir: sourceDir,
        host: selectedHost,
        job_name: jobName || undefined,
        cpus: cpus || undefined,
        mem: useMemory ? memory : undefined,
        time: timeLimit || undefined,
        partition: partition || undefined,
        ntasks_per_node: ntasksPerNode || undefined,
        // include alternate naming expected by backend
        n_tasks_per_node: ntasksPerNode || undefined,
        nodes: nodes || undefined,
        gpus_per_node: gpusPerNode || undefined,
        gres: gres || undefined,
        output: outputFile || undefined,
        error: errorFile || undefined,
        constraint: constraint || undefined,
        account: account || undefined,
        python_env: pythonEnv || undefined,
        exclude: excludePatterns,
        include: includePatterns,
        no_gitignore: noGitignore
      };

      const response = await axios.post<LaunchJobResponse>(`${API_BASE}/jobs/launch`, request);
      if (response.data.success) {
        success = `Job launched successfully! Job ID: ${response.data.job_id}`;
        // Reset some fields (keep directory and host)
        scriptContent = '#!/bin/bash\n\n# Your script here\necho "Hello, SLURM!"';
        jobName = '';
        outputFile = '';
        errorFile = '';
        constraint = '';
        account = '';
        gres = '';
        pythonEnv = '';
        uploadedScriptName = '';
        localScriptPath = '';
        scriptSource = 'editor';
        useMemory = false;
      } else {
        error = response.data.message;
      }
    } catch (err: unknown) {
      const axiosError = err as AxiosError;
      if (axiosError.response?.data?.detail) {
        error = axiosError.response.data.detail;
      } else {
        error = `Failed to launch job: ${axiosError.message}`;
      }
    } finally {
      launching = false;
    }
  }

  // Load entries for a server-local path using backend API
  async function loadLocalPath(path: string): Promise<void> {
    loading = true;
    try {
      const response = await axios.get(`${API_BASE}/local/list`, { 
        params: { 
          path,
          limit: maxEntries,
          show_hidden: showHiddenFiles,
          dirs_only: !showFilesInBrowser
        } 
      });
      localEntries = response.data.entries;
      currentLocalPath = response.data.path;
      
      // Clear any previous errors if successful
      error = null;
      
      // Show warning if we hit the limit (as info, not error)
      if (localEntries.length >= maxEntries) {
        console.log(`Directory listing limited to ${maxEntries} entries.`);
      }
    } catch (err: unknown) {
      const axiosError = err as AxiosError;
      error = `Failed to list local path: ${axiosError.message}`;
    } finally {
      loading = false;
    }
  }

  function selectCurrentLocalPath(): void {
    if (currentLocalPath) {
      sourceDir = currentLocalPath;
    }
  }

  function navigateUp(): void {
    if (currentLocalPath && currentLocalPath !== '/') {
      const parentPath = currentLocalPath.split('/').slice(0, -1).join('/') || '/';
      loadLocalPath(parentPath);
    }
  }

  function goToHome(): void {
    const homePath = '/home';
    loadLocalPath(homePath);
  }

  function goToRoot(): void {
    loadLocalPath('/');
  }

  function generateSlurmScript(...args: any[]): string {
    let script = '#!/bin/bash\n\n';
    
    // Header comment
    script += `# SLURM Job Script - Generated ${new Date().toLocaleString()}\n`;
    script += `# Host: ${selectedHost || '[Please select a host]'}\n`;
    script += `# Source: ${sourceDir || '[Please select source directory]'}\n\n`;
    
    // Add SLURM directives
    script += '# SLURM Configuration\n';
    if (jobName) script += `#SBATCH --job-name=${jobName}\n`;
    if (partition) script += `#SBATCH --partition=${partition}\n`;
    if (constraint) script += `#SBATCH --constraint=${constraint}\n`;
    if (account) script += `#SBATCH --account=${account}\n`;
    
    script += `#SBATCH --cpus-per-task=${cpus}\n`;
    if (useMemory) script += `#SBATCH --mem=${memory}GB\n`;
    script += `#SBATCH --time=${Math.floor(timeLimit/60)}:${String(timeLimit%60).padStart(2, '0')}:00\n`;
    script += `#SBATCH --nodes=${nodes}\n`;
    script += `#SBATCH --ntasks-per-node=${ntasksPerNode}\n`;
    
    if (gpusPerNode > 0) script += `#SBATCH --gpus-per-node=${gpusPerNode}\n`;
    if (gres) script += `#SBATCH --gres=${gres}\n`;
    if (outputFile) script += `#SBATCH --output=${outputFile}\n`;
    if (errorFile) script += `#SBATCH --error=${errorFile}\n`;
    
    if (pythonEnv) {
      script += '\n# Python environment activation\n';
      script += `${pythonEnv}\n`;
    }
    
    script += '\n# Job execution\n';
    script += 'cd "$SLURM_SUBMIT_DIR" || exit 1\n';
    script += 'echo "=== Job Information ==="\n';
    script += 'echo "Job ID: $SLURM_JOB_ID"\n';
    script += 'echo "Node: $(hostname)"\n';
    script += 'echo "Started: $(date)"\n';
    script += 'echo "Working directory: $(pwd)"\n';
    script += 'echo "======================"\n\n';
    
    // Add user script content
    script += '# User Script Content\n';
    if (scriptSource === 'editor') {
      const lines = scriptContent.split('\n');
      script += lines.map(line => line.startsWith('#') ? line : line).join('\n');
    } else if (scriptSource === 'local') {
      script += `# Execute local script: ${localScriptPath}\n`;
      script += `if [ -f "./${localScriptPath}" ]; then\n`;
      script += `    chmod +x "./${localScriptPath}"\n`;
      script += `    ./${localScriptPath}\n`;
      script += 'else\n';
      script += `    echo "ERROR: Script ${localScriptPath} not found!"\n`;
      script += '    exit 1\n';
      script += 'fi';
    } else if (scriptSource === 'upload') {
      script += `# Uploaded script: ${uploadedScriptName}\n`;
      script += scriptContent;
    }
    
    script += '\n\n# Job completion\n';
    script += 'echo "=== Job Completed ==="\n';
    script += 'echo "Finished: $(date)"\n';
    script += 'echo "Exit code: $?"\n';
    script += 'echo "===================="\n';
    
    return script;
  }


  function saveScript(): void {
    const blob = new Blob([generatedScript], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${jobName || 'slurm-job'}.sh`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }
</script>

<div class="launch-container">
  {#if error}
    <div class="error-message">
      <svg viewBox="0 0 24 24" fill="currentColor">
        <path d="M12,2C17.53,2 22,6.47 22,12C22,17.53 17.53,22 12,22C6.47,22 2,17.53 2,12C2,6.47 6.47,2 12,2M15.59,7L12,10.59L8.41,7L7,8.41L10.59,12L7,15.59L8.41,17L12,13.41L15.59,17L17,15.59L13.41,12L17,8.41L15.59,7Z"/>
      </svg>
      {error}
    </div>
  {/if}

  {#if success}
    <div class="success-message">
      <svg viewBox="0 0 24 24" fill="currentColor">
        <path d="M12,2C17.53,2 22,6.47 22,12C22,17.53 17.53,22 12,22C6.47,22 2,17.53 2,12C2,6.47 6.47,2 12,2M17,9L12,14L7,9L8.41,7.59L12,11.17L15.59,7.59L17,9Z"/>
      </svg>
      {success}
    </div>
  {/if}

  <div class="main-layout">
    <!-- Top Section: Left (Config Forms) + Right (Script Preview) -->
    <div class="top-section">
      <!-- Left Panel: Main Configuration Forms -->
      <div class="config-panel">
        <div class="config-content">
          <form id="launch-form" on:submit|preventDefault={launchJob} class="launch-form">
            <!-- Host Selection -->
            <section class="form-section">
              <h3>Target Host</h3>
              <div class="field">
                <label for="host">SLURM Host *</label>
                <select id="host" bind:value={selectedHost} required disabled={loading}>
                  {#if loading}
                    <option>Loading hosts...</option>
                  {:else}
                    {#each hosts as host}
                      <option value={host.hostname}>{host.hostname}</option>
                    {/each}
                  {/if}
                </select>
              </div>
            </section>

            <!-- Source Directory -->
            <section class="form-section">
              <h3>Source Directory</h3>
              <div class="field">
                <label for="source-dir">Local Directory Path *</label>
                <input
                  id="source-dir"
                  type="text"
                  bind:value={sourceDir}
                  placeholder="/path/to/your/project"
                  required
                />

                <!-- Local filesystem browser -->
                <div class="local-browser">
                  <div class="browser-nav">
                    <button type="button" on:click={goToRoot} class="nav-btn">Root</button>
                    <button type="button" on:click={goToHome} class="nav-btn">Home</button>
                    <button type="button" on:click={navigateUp} disabled={currentLocalPath === '/'} class="nav-btn">Up</button>
                    <button type="button" on:click={() => loadLocalPath(currentLocalPath)} disabled={!currentLocalPath} class="nav-btn">Refresh</button>
                  </div>

                  <div class="browser-path">
                    <strong>Current:</strong> {currentLocalPath || '/'}
                    <button type="button" on:click={selectCurrentLocalPath} disabled={!currentLocalPath} class="select-btn">Select This Directory</button>
                  </div>

                  <div class="browser-options">
                    <label class="checkbox-label">
                      <input type="checkbox" bind:checked={showHiddenFiles} on:change={() => loadLocalPath(currentLocalPath)} />
                      Show hidden files
                    </label>
                    <label class="checkbox-label">
                      <input type="checkbox" bind:checked={showFilesInBrowser} on:change={() => loadLocalPath(currentLocalPath)} />
                      Show files (directories only by default)
                    </label>
                    <div class="limit-info">Showing max {maxEntries} entries</div>
                  </div>

                  <ul class="browser-list">
                    {#if localEntries && localEntries.length > 0}
                      {#each localEntries as entry}
                        <li class="browser-entry {entry.is_dir ? 'dir' : 'file'}">
                          {#if entry.is_dir}
                            <button type="button" class="dir-button" on:click={() => loadLocalPath(entry.path)}>{entry.name}/</button>
                          {:else}
                            <span class="file-name">{entry.name}</span>
                          {/if}
                        </li>
                      {/each}
                    {:else}
                      <li class="browser-entry">No entries</li>
                    {/if}
                  </ul>
                </div>
              </div>
            </section>

            <!-- Script Content -->
            <section class="form-section">
              <h3>Job Script</h3>
              <div class="field">
                <label>Script Source</label>
                <div class="script-source">
                  <label><input type="radio" bind:group={scriptSource} value="editor" /> Editor</label>
                  <label><input type="radio" bind:group={scriptSource} value="local" /> Local file (in source dir)</label>
                  <label><input type="radio" bind:group={scriptSource} value="upload" /> Upload file</label>
                </div>

                {#if scriptSource === 'editor'}
                  <label for="script">Script Content *</label>
                  <textarea
                    id="script"
                    bind:value={scriptContent}
                    rows="12"
                    placeholder="#\!/bin/bash&#10;&#10;# Your SLURM job script here"
                    required
                  ></textarea>
                {/if}

                {#if scriptSource === 'local'}
                  <label for="local-script">Local script path (relative to source dir) *</label>
                  <input id="local-script" type="text" bind:value={localScriptPath} placeholder="scripts/run.sh" />
                  <div class="field-help">Provide the path to the script inside the source directory you selected above.</div>
                {/if}

                {#if scriptSource === 'upload'}
                  <label>Upload script file *</label>
                  <input type="file" accept=".sh,application/x-shellscript,text/*" on:change={handleScriptUpload} />
                  {#if uploadedScriptName}
                    <div class="field-help">Uploaded: {uploadedScriptName}</div>
                  {/if}
                {/if}

                <div class="field-help">
                  Shell script or SLURM batch script. SLURM directives will be added automatically for shell scripts when possible.
                </div>
              </div>
            </section>

            <!-- SLURM Parameters -->
            <section class="form-section">
              <h3>SLURM Parameters</h3>
              <div class="field-group">
                <div class="field">
                  <label for="job-name">Job Name</label>
                  <input id="job-name" type="text" bind:value={jobName} placeholder="my-job" />
                </div>

                <div class="field">
                  <label for="partition">Partition</label>
                  <input id="partition" type="text" bind:value={partition} placeholder="gpu" />
                </div>
              </div>

              <div class="field-group">
                <div class="field">
                  <label for="constraint">Constraint</label>
                  <input id="constraint" type="text" bind:value={constraint} placeholder="gpu" />
                  <div class="field-help">
                    Node constraints (e.g., "gpu", "bigmem", "intel")
                  </div>
                </div>

                <div class="field">
                  <label for="account">Account</label>
                  <input id="account" type="text" bind:value={account} placeholder="project-123" />
                  <div class="field-help">
                    SLURM account for billing purposes
                  </div>
                </div>
              </div>

              <div class="field-group">
                <div class="field">
                  <label for="cpus">CPUs: {cpus}</label>
                  <input
                    id="cpus"
                    type="range"
                    min="1"
                    max="64"
                    bind:value={cpus}
                    class="slider"
                  />
                </div>

                <div class="field">
                  <label>Memory</label>
                  <div class="memory-row">
                    <label class="small"><input type="checkbox" bind:checked={useMemory} /> Specify memory</label>
                    {#if useMemory}
                      <div class="memory-slider">
                        <label for="memory">{formatMemoryLabel(memory)}</label>
                        <input id="memory" type="range" min="1" max="512" bind:value={memory} class="slider" />
                      </div>
                    {/if}
                  </div>
                </div>
              </div>

              <div class="field-group">
                <div class="field">
                  <label for="nodes">Nodes: {nodes}</label>
                  <input
                    id="nodes"
                    type="range"
                    min="1"
                    max="16"
                    bind:value={nodes}
                    class="slider"
                  />
                </div>

                <div class="field">
                  <label for="ntasks-per-node">Tasks per Node: {ntasksPerNode}</label>
                  <input
                    id="ntasks-per-node"
                    type="range"
                    min="1"
                    max="128"
                    bind:value={ntasksPerNode}
                    class="slider"
                  />
                </div>
              </div>

              <div class="field-group">
                <div class="field">
                  <label for="gpus-per-node">GPUs per Node: {gpusPerNode}</label>
                  <input
                    id="gpus-per-node"
                    type="range"
                    min="0"
                    max="8"
                    bind:value={gpusPerNode}
                    class="slider"
                  />
                </div>

                <div class="field">
                  <label for="gres">Generic Resources</label>
                  <input id="gres" type="text" bind:value={gres} placeholder="gpu:tesla:2" />
                  <div class="field-help">
                    Generic resource specification (e.g., "gpu:tesla:2")
                  </div>
                </div>
              </div>

              <div class="field">
                <label for="time">Time Limit: {formatTimeLabel(timeLimit)}</label>
                <input
                  id="time"
                  type="range"
                  min="5"
                  max="2880"
                  step="5"
                  bind:value={timeLimit}
                  class="slider"
                />
              </div>

              <div class="field-group">
                <div class="field">
                  <label for="output">Output File</label>
                  <input
                    id="output"
                    type="text"
                    bind:value={outputFile}
                    placeholder="job-%j.out"
                  />
                </div>

                <div class="field">
                  <label for="error">Error File</label>
                  <input
                    id="error"
                    type="text"
                    bind:value={errorFile}
                    placeholder="job-%j.err"
                  />
                </div>
              </div>

              <div class="field">
                <label for="python-env">Python Environment Setup</label>
                <input
                  id="python-env"
                  type="text"
                  bind:value={pythonEnv}
                  placeholder="conda activate myenv"
                />
                <div class="field-help">
                  Command to set up Python environment (e.g., conda activate, source venv/bin/activate)
                </div>
              </div>
            </section>

          </form>
        </div>
      </div>

      <!-- Right Column: Script Preview + Sync Settings -->
      <div class="right-column">
        <div class="right-scroll-container">
          <!-- Script Preview Panel -->
          <div class="preview-panel">
          <div class="preview-header">
            <h3>Generated Script Preview</h3>
            <div class="preview-stats">
              <span class="stat-item">Lines: {generatedScript.split('\n').length}</span>
              <span class="stat-item">Size: {new Blob([generatedScript]).size} bytes</span>
              {#if !selectedHost || !sourceDir}
                <span class="stat-item warning">⚠️ Missing config</span>
              {/if}
            </div>
          </div>
          
          <div class="preview-content">
            <pre class="script-preview"><code>{generatedScript}</code></pre>
          </div>
          
          <div class="preview-actions">
            <button type="button" class="secondary-btn" on:click={() => navigator.clipboard.writeText(generatedScript)}>
              Copy Script
            </button>
            <button type="button" class="secondary-btn" on:click={saveScript}>
              Save as File
            </button>
            <button type="button" class="launch-button" on:click={launchJob} disabled={launching || loading}>
              {#if launching}
                <svg class="loading-spinner" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12,4V2A10,10 0 0,0 2,12H4A8,8 0 0,1 12,4Z"/>
                </svg>
                Launching...
              {:else}
                Launch Job
              {/if}
            </button>
          </div>
        </div>

        <!-- Sync Settings Panel -->
        <div class="sync-panel">
          <section class="form-section sync-section">
            <h3>Sync Settings</h3>
            
            <div class="sync-content">
              <div class="field">
                <label>
                  <input type="checkbox" bind:checked={noGitignore} />
                  Disable .gitignore
                </label>
                <div class="field-help">
                  By default, patterns from .gitignore are excluded from sync
                </div>
              </div>

              <div class="field">
                <label>Exclude Patterns</label>
                <div class="pattern-input">
                  <input
                    type="text"
                    bind:value={currentExcludePattern}
                    placeholder="*.log"
                    on:keydown={(e) => e.key === 'Enter' && addExcludePattern()}
                  />
                  <button type="button" on:click={addExcludePattern}>Add</button>
                </div>
                <div class="pattern-list">
                  {#each excludePatterns as pattern, index}
                    <span class="pattern-tag">
                      {pattern}
                      <button
                        type="button"
                        class="remove-pattern"
                        on:click={() => removeExcludePattern(index)}
                      >×</button>
                    </span>
                  {/each}
                </div>
              </div>

              <div class="field">
                <label>Include Patterns (override .gitignore)</label>
                <div class="pattern-input">
                  <input
                    type="text"
                    bind:value={currentIncludePattern}
                    placeholder="data/*.csv"
                    on:keydown={(e) => e.key === 'Enter' && addIncludePattern()}
                  />
                  <button type="button" on:click={addIncludePattern}>Add</button>
                </div>
                <div class="pattern-list">
                  {#each includePatterns as pattern, index}
                    <span class="pattern-tag">
                      {pattern}
                      <button
                        type="button"
                        class="remove-pattern"
                        on:click={() => removeIncludePattern(index)}
                      >×</button>
                    </span>
                  {/each}
                </div>
              </div>
            </div>
          </section>
        </div>
        </div>
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

  .top-section {
    display: contents;
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
  .right-scroll-container::-webkit-scrollbar {
    width: 8px;
  }

  .right-scroll-container::-webkit-scrollbar-track {
    background: transparent;
  }

  .right-scroll-container::-webkit-scrollbar-thumb {
    background: rgba(156, 163, 175, 0.5);
    border-radius: 4px;
  }

  .right-scroll-container::-webkit-scrollbar-thumb:hover {
    background: rgba(156, 163, 175, 0.7);
  }

  .preview-panel {
    flex: 1;
    display: flex;
    flex-direction: column;
    background: #1e1e2e;
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    min-height: 300px;
    max-height: 500px;
  }

  .preview-content {
    flex: 1;
    overflow: auto;
    background: #2d3748;
    min-height: 0;
  }

  .preview-content::-webkit-scrollbar {
    width: 8px;
  }

  .preview-content::-webkit-scrollbar-track {
    background: rgba(255, 255, 255, 0.05);
  }

  .preview-content::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.2);
    border-radius: 4px;
  }

  .preview-content::-webkit-scrollbar-thumb:hover {
    background: rgba(255, 255, 255, 0.3);
  }

  .sync-panel {
    flex: 0 0 auto;
    min-height: 250px;
    max-height: 400px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    background: white;
    border-radius: 12px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  }

  .sync-section {
    margin-bottom: 0;
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    padding: 1.25rem;
  }

  .sync-section h3 {
    flex-shrink: 0;
  }

  .sync-content {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 1rem;
    overflow-y: auto;
    overflow-x: hidden;
    padding-right: 0.5rem;
    min-height: 0;
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

  .launch-form {
    display: block;
    gap: 1.5rem;
    padding: 1.5rem 1.5rem 2.5rem 1.5rem;
    background: white;
    border-radius: 12px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  }

  .preview-header {
    background: linear-gradient(135deg, #2d3748 0%, #1a202c 100%);
    color: white;
    padding: 1rem 1.5rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  }

  .preview-header h3 {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
  }

  .preview-stats {
    display: flex;
    gap: 1rem;
  }

  .stat-item {
    font-size: 0.8rem;
    color: rgba(255, 255, 255, 0.7);
    background: rgba(255, 255, 255, 0.1);
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
  }

  .stat-item.warning {
    background: rgba(245, 158, 11, 0.2);
    color: #fbbf24;
    border: 1px solid rgba(245, 158, 11, 0.3);
  }

  .script-preview {
    margin: 0;
    padding: 1.5rem;
    font-family: 'JetBrains Mono', 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
    font-size: 0.875rem;
    line-height: 1.6;
    color: #e2e8f0;
    background: transparent;
    white-space: pre-wrap;
    word-wrap: break-word;
  }

  .script-preview code {
    color: #e2e8f0;
  }


  .preview-actions {
    padding: 1rem 1.5rem;
    background: #1a202c;
    border-top: 1px solid rgba(255, 255, 255, 0.1);
    display: flex;
    gap: 0.75rem;
  }

  .secondary-btn {
    padding: 0.5rem 1rem;
    background: rgba(255, 255, 255, 0.1);
    color: white;
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 6px;
    font-size: 0.875rem;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .secondary-btn:hover {
    background: rgba(255, 255, 255, 0.2);
    transform: translateY(-1px);
  }

  .form-section {
    background: #fafbfc;
    border: 1px solid #e1e5e9;
    border-radius: 10px;
    padding: 1.25rem;
    transition: all 0.2s ease;
    margin-bottom: 1rem;
  }

  .form-section:hover {
    border-color: #c7d2fe;
    box-shadow: 0 2px 8px rgba(99, 102, 241, 0.1);
  }

  .form-section:last-child {
    margin-bottom: 0;
  }

  .form-section h3 {
    margin: 0 0 1.25rem 0;
    color: #374151;
    font-size: 1.125rem;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .form-section h3::before {
    content: '';
    width: 4px;
    height: 20px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 2px;
  }

  .field {
    margin-bottom: 1rem;
  }

  .field:last-child {
    margin-bottom: 0;
  }

  .field-group {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1rem;
  }

  .field label {
    display: block;
    margin-bottom: 0.25rem;
    font-weight: 500;
    color: var(--color-text-primary);
    font-size: 0.9rem;
  }

  .field input[type="text"],
  .field input[type="number"],
  .field select,
  .field textarea {
    width: 100%;
    padding: 0.75rem;
    border: 1.5px solid #e5e7eb;
    border-radius: 8px;
    background: white;
    color: #374151;
    font-family: inherit;
    font-size: 0.9rem;
    transition: all 0.2s ease;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  }

  .field textarea {
    font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
    resize: vertical;
    min-height: 200px;
  }

  .field input:focus,
  .field select:focus,
  .field textarea:focus {
    outline: none;
    border-color: #667eea;
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1), 0 2px 4px rgba(0, 0, 0, 0.1);
    transform: translateY(-1px);
  }

  .field input:disabled,
  .field select:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .field-help {
    margin-top: 0.25rem;
    font-size: 0.8rem;
    color: var(--color-text-secondary);
  }

  .field-row {
    display: flex;
    gap: 1rem;
    align-items: center;
    margin-top: 0.5rem;
  }

  .script-source {
    display: flex;
    gap: 1rem;
    margin-bottom: 0.5rem;
  }

  .memory-row {
    display: flex;
    gap: 1rem;
    align-items: center;
  }

  .memory-slider { width: 100%; }

  label.small { font-size: 0.85rem; color: var(--color-text-secondary); }

  input[type="file"][webkitdirectory] { font-size: 0.85rem; }

  .slider {
    width: 100%;
    height: 8px;
    border-radius: 4px;
    background: linear-gradient(90deg, #e5e7eb 0%, #f3f4f6 100%);
    outline: none;
    -webkit-appearance: none;
    transition: all 0.2s ease;
  }

  .slider:hover {
    background: linear-gradient(90deg, #d1d5db 0%, #e5e7eb 100%);
  }

  .slider::-webkit-slider-thumb {
    -webkit-appearance: none;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    cursor: pointer;
    box-shadow: 0 2px 6px rgba(102, 126, 234, 0.3);
    transition: all 0.2s ease;
  }

  .slider::-webkit-slider-thumb:hover {
    transform: scale(1.1);
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
  }

  .slider::-moz-range-thumb {
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    cursor: pointer;
    border: none;
    box-shadow: 0 2px 6px rgba(102, 126, 234, 0.3);
    transition: all 0.2s ease;
  }

  .slider::-moz-range-thumb:hover {
    transform: scale(1.1);
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
  }

  .pattern-input {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 0.5rem;
  }

  .pattern-input input {
    flex: 1;
  }

  .pattern-input button {
    padding: 0.5rem 1rem;
    background: var(--color-accent);
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.9rem;
  }

  .pattern-input button:hover {
    background: var(--color-accent-hover);
  }

  .pattern-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .pattern-tag {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.25rem 0.5rem;
    background: var(--color-surface-hover);
    border: 1px solid var(--color-border);
    border-radius: 16px;
    font-size: 0.8rem;
    color: var(--color-text-primary);
  }

  .remove-pattern {
    background: none;
    border: none;
    color: var(--color-text-secondary);
    cursor: pointer;
    padding: 0;
    width: 1rem;
    height: 1rem;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1rem;
    line-height: 1;
  }

  .remove-pattern:hover {
    background: var(--color-error);
    color: white;
  }


  .launch-button {
    flex: 1;
    padding: 0.75rem 1.25rem;
    background: linear-gradient(135deg, #10b981 0%, #059669 100%);
    color: white;
    border: none;
    border-radius: 8px;
    font-size: 0.95rem;
    font-weight: 600;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    transition: all 0.2s ease;
    box-shadow: 0 2px 8px rgba(16, 185, 129, 0.3);
  }

  .launch-button:hover:not(:disabled) {
    background: linear-gradient(135deg, #059669 0%, #047857 100%);
    transform: translateY(-1px);
    box-shadow: 0 4px 16px rgba(16, 185, 129, 0.4);
  }

  .launch-button:active:not(:disabled) {
    transform: translateY(0);
  }

  .launch-button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
    transform: none;
  }

  .loading-spinner {
    width: 1.2rem;
    height: 1.2rem;
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }

  /* Checkbox styling */
  input[type="checkbox"] {
    width: auto;
    margin-right: 0.5rem;
  }

  /* Directory browser styles */
  .local-browser {
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    margin-top: 1rem;
    overflow: hidden;
    background: white;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  }

  .browser-nav {
    display: flex;
    gap: 0.5rem;
    padding: 1rem;
    border-bottom: 1px solid #f3f4f6;
    background: linear-gradient(90deg, #f8fafc 0%, #f1f5f9 100%);
  }

  .nav-btn {
    padding: 0.5rem 1rem;
    font-size: 0.875rem;
    background: white;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    cursor: pointer;
    color: #374151;
    font-weight: 500;
    transition: all 0.2s ease;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  }

  .nav-btn:hover:not(:disabled) {
    background: #f9fafb;
    border-color: #9ca3af;
    transform: translateY(-1px);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  }

  .nav-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
    transform: none;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  }

  .browser-path {
    padding: 0.75rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: var(--color-surface);
    border-bottom: 1px solid var(--color-border);
    font-size: 0.9rem;
  }

  .select-btn {
    padding: 0.4rem 0.8rem;
    font-size: 0.85rem;
    background: var(--color-accent);
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
  }

  .select-btn:hover:not(:disabled) {
    background: var(--color-accent-hover);
  }

  .select-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .browser-options {
    padding: 0.5rem 0.75rem;
    background: var(--color-surface);
    border-bottom: 1px solid var(--color-border);
    display: flex;
    gap: 1rem;
    align-items: center;
    font-size: 0.85rem;
  }

  .checkbox-label {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    font-size: 0.85rem;
    color: var(--color-text-secondary);
    margin: 0;
  }

  .limit-info {
    color: var(--color-text-secondary);
    font-size: 0.8rem;
    margin-left: auto;
  }

  .browser-list {
    max-height: 300px;
    overflow-y: auto;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .browser-entry {
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid var(--color-border-light);
  }

  .browser-entry:last-child {
    border-bottom: none;
  }

  .browser-entry.dir {
    background: var(--color-surface);
  }

  .browser-entry.file {
    background: var(--color-background);
    color: var(--color-text-secondary);
  }

  .dir-button {
    background: none;
    border: none;
    color: var(--color-accent);
    cursor: pointer;
    font-size: 0.9rem;
    padding: 0;
    text-align: left;
    width: 100%;
  }

  .dir-button:hover {
    text-decoration: underline;
  }

  .file-name {
    font-size: 0.9rem;
    color: var(--color-text-secondary);
  }

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

    .preview-panel {
      flex: 2;
      min-height: 250px;
      max-height: none;
    }

    .sync-panel {
      flex: 1;
      min-height: 200px;
      max-height: none;
    }
  }

  @media (max-width: 768px) {
    .launch-container {
      height: 100vh;
      overflow: hidden;
    }

    .main-layout {
      padding: 0.75rem;
      gap: 0.75rem;
      flex-direction: column;
      height: calc(100vh - 1.5rem);
      box-sizing: border-box;
    }

    .config-panel {
      flex: 1;
      max-height: 60vh;
      min-height: 300px;
      overflow: hidden;
    }

    .config-content {
      height: 100%;
    }

    .right-column {
      flex: 1;
      max-height: 35vh;
      min-height: 200px;
    }

    .right-scroll-container {
      flex-direction: column;
      gap: 0.75rem;
      height: 100%;
    }

    .preview-panel {
      flex: 1;
      min-height: 150px;
      max-height: 200px;
    }
    
    .sync-panel {
      flex: 1;
      min-height: 120px;
      max-height: 150px;
    }

    .field-group {
      grid-template-columns: 1fr;
      gap: 0.75rem;
    }

    .form-section {
      padding: 0.875rem;
      border-radius: 8px;
    }

    .browser-nav {
      padding: 0.5rem;
      flex-wrap: wrap;
      gap: 0.375rem;
    }

    .nav-btn {
      padding: 0.375rem 0.625rem;
      font-size: 0.8rem;
    }

    .browser-path {
      padding: 0.625rem;
      flex-direction: column;
      align-items: flex-start;
      gap: 0.5rem;
    }

    .select-btn {
      align-self: stretch;
      text-align: center;
    }

    .launch-button {
      font-size: 0.85rem;
      padding: 0.625rem 1rem;
      flex: 1;
      min-width: 0;
    }

    .preview-header {
      padding: 0.625rem 0.875rem;
    }

    .preview-stats {
      flex-direction: column;
      gap: 0.25rem;
      align-items: flex-start;
    }

    .stat-item {
      font-size: 0.7rem;
      padding: 0.2rem 0.4rem;
    }

    .script-preview {
      padding: 0.875rem;
      font-size: 0.75rem;
      line-height: 1.4;
    }

    .preview-actions {
      padding: 0.625rem 0.875rem;
      gap: 0.5rem;
      flex-wrap: wrap;
    }

    .secondary-btn {
      font-size: 0.8rem;
      padding: 0.375rem 0.75rem;
      flex: 1;
      min-width: 0;
    }

    .browser-list {
      max-height: 200px;
    }

    .memory-row {
      flex-direction: column;
      align-items: flex-start;
      gap: 0.5rem;
    }

    .memory-slider {
      width: 100%;
    }
  }

  @media (max-width: 480px) {
    .main-layout {
      padding: 0.5rem;
      gap: 0.5rem;
      height: calc(100vh - 1rem);
    }

    .config-panel {
      max-height: 65vh;
      min-height: 250px;
    }

    .right-column {
      max-height: 30vh;
      min-height: 180px;
    }

    .preview-panel {
      min-height: 120px;
      max-height: 150px;
    }

    .sync-panel {
      min-height: 100px;
      max-height: 120px;
    }

    .form-section {
      padding: 0.75rem;
      margin-bottom: 0.75rem;
    }

    .browser-nav {
      padding: 0.375rem;
      gap: 0.25rem;
    }

    .nav-btn {
      padding: 0.25rem 0.5rem;
      font-size: 0.75rem;
    }
  }

  /* Improved scrollbar for config content */
  .config-content::-webkit-scrollbar {
    width: 6px;
  }

  .config-content::-webkit-scrollbar-track {
    background: transparent;
  }

  .config-content::-webkit-scrollbar-thumb {
    background: rgba(156, 163, 175, 0.4);
    border-radius: 3px;
  }

  .config-content::-webkit-scrollbar-thumb:hover {
    background: rgba(156, 163, 175, 0.6);
  }

  /* Improved scrollbar for browser list */
  .browser-list::-webkit-scrollbar {
    width: 6px;
  }

  .browser-list::-webkit-scrollbar-track {
    background: transparent;
  }

  .browser-list::-webkit-scrollbar-thumb {
    background: rgba(156, 163, 175, 0.4);
    border-radius: 3px;
  }

  .browser-list::-webkit-scrollbar-thumb:hover {
    background: rgba(156, 163, 175, 0.6);
  }

  /* Improved scrollbar for sync content */
  .sync-content::-webkit-scrollbar {
    width: 6px;
  }

  .sync-content::-webkit-scrollbar-track {
    background: transparent;
  }

  .sync-content::-webkit-scrollbar-thumb {
    background: rgba(156, 163, 175, 0.4);
    border-radius: 3px;
  }

  .sync-content::-webkit-scrollbar-thumb:hover {
    background: rgba(156, 163, 175, 0.6);
  }
</style>
