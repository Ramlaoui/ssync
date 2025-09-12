<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  
  export let hostname = '';
  export let config = {
    job_name: '',
    cpus: 4,
    mem: 16, // GB
    time: 120, // minutes
    partition: '',
    account: '',
    nodes: 1,
    ntasks_per_node: 1,
    gpus_per_node: 0,
    constraint: '',
    output: 'job_%j.out',
    error: 'job_%j.err'
  };
  
  const dispatch = createEventDispatcher();
  
  // Resource presets
  const presets = [
    { name: 'Small CPU', cpus: 2, mem: 8, gpus: 0, time: 60 },
    { name: 'Medium CPU', cpus: 8, mem: 32, gpus: 0, time: 180 },
    { name: 'Large CPU', cpus: 32, mem: 128, gpus: 0, time: 360 },
    { name: 'Single GPU', cpus: 8, mem: 32, gpus: 1, time: 240 },
    { name: 'Multi GPU', cpus: 16, mem: 64, gpus: 4, time: 480 },
    { name: 'Memory Heavy', cpus: 4, mem: 256, gpus: 0, time: 120 }
  ];
  
  // Partition options per cluster
  const partitionOptions: Record<string, string[]> = {
    jz: ['cpu_p1', 'gpu_p1', 'gpu_p2', 'gpu_p5'],
    adastra: ['cpu', 'gpu', 'bigmem'],
    entalpic: ['cpu', 'gpu'],
    mbp: ['local']
  };
  
  // Validation state
  let errors: Record<string, string> = {};
  let warnings: Record<string, string> = {};
  
  function applyPreset(preset: typeof presets[0]) {
    config.cpus = preset.cpus;
    config.mem = preset.mem;
    config.gpus_per_node = preset.gpus;
    config.time = preset.time;
    dispatch('change', config);
    validateConfig();
  }
  
  function formatTime(minutes: number): string {
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return `${hours.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:00`;
  }
  
  function parseTime(timeStr: string): number {
    const parts = timeStr.split(':');
    if (parts.length === 3) {
      return parseInt(parts[0]) * 60 + parseInt(parts[1]);
    }
    return 120; // default
  }
  
  function validateConfig() {
    errors = {};
    warnings = {};
    
    // Validate resources
    if (config.cpus < 1) {
      errors.cpus = 'At least 1 CPU required';
    } else if (config.cpus > 128) {
      warnings.cpus = 'Very high CPU count - verify availability';
    }
    
    if (config.mem < 1) {
      errors.mem = 'At least 1 GB memory required';
    } else if (config.mem > 512) {
      warnings.mem = 'Very high memory - consider bigmem partition';
    }
    
    if (config.time < 1) {
      errors.time = 'Minimum time is 1 minute';
    } else if (config.time > 1440) {
      warnings.time = 'Jobs over 24 hours may have longer queue times';
    }
    
    // Check GPU/partition compatibility
    if (config.gpus_per_node > 0 && config.partition && !config.partition.includes('gpu')) {
      warnings.partition = 'GPU requested but partition may not have GPUs';
    }
    
    // Check job name
    if (!config.job_name) {
      warnings.job_name = 'Consider adding a descriptive job name';
    }
    
    dispatch('validate', { errors, warnings });
  }
  
  function handleChange() {
    dispatch('change', config);
    validateConfig();
  }
  
  function generateSBATCHPreview(): string {
    let preview = '#!/bin/bash\n';
    if (config.job_name) preview += `#SBATCH --job-name=${config.job_name}\n`;
    if (config.partition) preview += `#SBATCH --partition=${config.partition}\n`;
    if (config.account) preview += `#SBATCH --account=${config.account}\n`;
    preview += `#SBATCH --nodes=${config.nodes}\n`;
    preview += `#SBATCH --ntasks-per-node=${config.ntasks_per_node}\n`;
    preview += `#SBATCH --cpus-per-task=${config.cpus}\n`;
    preview += `#SBATCH --mem=${config.mem}G\n`;
    preview += `#SBATCH --time=${formatTime(config.time)}\n`;
    if (config.gpus_per_node > 0) {
      preview += `#SBATCH --gres=gpu:${config.gpus_per_node}\n`;
    }
    if (config.constraint) preview += `#SBATCH --constraint=${config.constraint}\n`;
    preview += `#SBATCH --output=${config.output}\n`;
    preview += `#SBATCH --error=${config.error}\n`;
    return preview;
  }
  
  $: sbatchPreview = generateSBATCHPreview();
  $: availablePartitions = partitionOptions[hostname] || [];
</script>

<div class="config-panel">
  <div class="panel-header">
    <h3>Job Configuration</h3>
    <button class="preview-toggle" on:click={() => dispatch('togglePreview')}>
      <svg viewBox="0 0 24 24" fill="currentColor">
        <path d="M12,9A3,3 0 0,0 9,12A3,3 0 0,0 12,15A3,3 0 0,0 15,12A3,3 0 0,0 12,9M12,17A5,5 0 0,0 7,12A5,5 0 0,0 12,7A5,5 0 0,0 17,12A5,5 0 0,0 12,17M12,4.5C7,4.5 2.73,7.61 1,12C2.73,16.39 7,19.5 12,19.5C17,19.5 21.27,16.39 23,12C21.27,7.61 17,4.5 12,4.5Z"/>
      </svg>
      Preview
    </button>
  </div>
  
  <!-- Resource Presets -->
  <div class="section">
    <label class="section-label">Quick Presets</label>
    <div class="presets-grid">
      {#each presets as preset}
        <button 
          class="preset-btn"
          on:click={() => applyPreset(preset)}
          title="{preset.cpus} CPUs, {preset.mem}GB RAM, {preset.gpus} GPUs, {preset.time} min"
        >
          {preset.name}
        </button>
      {/each}
    </div>
  </div>
  
  <!-- Basic Settings -->
  <div class="section">
    <label class="section-label">Basic Settings</label>
    
    <div class="form-group">
      <label for="job_name">
        Job Name
        {#if warnings.job_name}
          <span class="warning">⚠ {warnings.job_name}</span>
        {/if}
      </label>
      <input 
        id="job_name"
        type="text"
        bind:value={config.job_name}
        on:change={handleChange}
        placeholder="my_experiment"
        class:has-warning={warnings.job_name}
      />
    </div>
    
    <div class="form-row">
      <div class="form-group">
        <label for="partition">
          Partition
          {#if warnings.partition}
            <span class="warning">⚠ {warnings.partition}</span>
          {/if}
        </label>
        <select 
          id="partition"
          bind:value={config.partition}
          on:change={handleChange}
          class:has-warning={warnings.partition}
        >
          <option value="">Default</option>
          {#each availablePartitions as partition}
            <option value={partition}>{partition}</option>
          {/each}
        </select>
      </div>
      
      <div class="form-group">
        <label for="account">Account</label>
        <input 
          id="account"
          type="text"
          bind:value={config.account}
          on:change={handleChange}
          placeholder="Optional"
        />
      </div>
    </div>
  </div>
  
  <!-- Resources -->
  <div class="section">
    <label class="section-label">Resources</label>
    
    <div class="form-row">
      <div class="form-group">
        <label for="cpus">
          CPUs per Task
          {#if errors.cpus}
            <span class="error">{errors.cpus}</span>
          {:else if warnings.cpus}
            <span class="warning">⚠ {warnings.cpus}</span>
          {/if}
        </label>
        <div class="input-with-slider">
          <input 
            id="cpus"
            type="number"
            bind:value={config.cpus}
            on:change={handleChange}
            min="1"
            max="128"
            class:has-error={errors.cpus}
            class:has-warning={warnings.cpus}
          />
          <input 
            type="range"
            bind:value={config.cpus}
            on:input={handleChange}
            min="1"
            max="128"
            class="slider"
          />
        </div>
      </div>
      
      <div class="form-group">
        <label for="mem">
          Memory (GB)
          {#if errors.mem}
            <span class="error">{errors.mem}</span>
          {:else if warnings.mem}
            <span class="warning">⚠ {warnings.mem}</span>
          {/if}
        </label>
        <div class="input-with-slider">
          <input 
            id="mem"
            type="number"
            bind:value={config.mem}
            on:change={handleChange}
            min="1"
            max="512"
            class:has-error={errors.mem}
            class:has-warning={warnings.mem}
          />
          <input 
            type="range"
            bind:value={config.mem}
            on:input={handleChange}
            min="1"
            max="512"
            class="slider"
          />
        </div>
      </div>
    </div>
    
    <div class="form-row">
      <div class="form-group">
        <label for="gpus">GPUs per Node</label>
        <div class="input-with-slider">
          <input 
            id="gpus"
            type="number"
            bind:value={config.gpus_per_node}
            on:change={handleChange}
            min="0"
            max="8"
          />
          <input 
            type="range"
            bind:value={config.gpus_per_node}
            on:input={handleChange}
            min="0"
            max="8"
            class="slider"
          />
        </div>
      </div>
      
      <div class="form-group">
        <label for="time">
          Time Limit (minutes)
          {#if errors.time}
            <span class="error">{errors.time}</span>
          {:else if warnings.time}
            <span class="warning">⚠ {warnings.time}</span>
          {/if}
        </label>
        <div class="time-input">
          <input 
            id="time"
            type="number"
            bind:value={config.time}
            on:change={handleChange}
            min="1"
            max="2880"
            class:has-error={errors.time}
            class:has-warning={warnings.time}
          />
          <span class="time-display">{formatTime(config.time)}</span>
        </div>
      </div>
    </div>
  </div>
  
  <!-- Advanced -->
  <details class="section">
    <summary class="section-label clickable">Advanced Settings</summary>
    
    <div class="form-row">
      <div class="form-group">
        <label for="nodes">Nodes</label>
        <input 
          id="nodes"
          type="number"
          bind:value={config.nodes}
          on:change={handleChange}
          min="1"
          max="100"
        />
      </div>
      
      <div class="form-group">
        <label for="ntasks">Tasks per Node</label>
        <input 
          id="ntasks"
          type="number"
          bind:value={config.ntasks_per_node}
          on:change={handleChange}
          min="1"
          max="128"
        />
      </div>
    </div>
    
    <div class="form-group">
      <label for="constraint">Node Constraint</label>
      <input 
        id="constraint"
        type="text"
        bind:value={config.constraint}
        on:change={handleChange}
        placeholder="e.g., v100-32g"
      />
    </div>
    
    <div class="form-row">
      <div class="form-group">
        <label for="output">Output File</label>
        <input 
          id="output"
          type="text"
          bind:value={config.output}
          on:change={handleChange}
        />
      </div>
      
      <div class="form-group">
        <label for="error">Error File</label>
        <input 
          id="error"
          type="text"
          bind:value={config.error}
          on:change={handleChange}
        />
      </div>
    </div>
  </details>
  
  <!-- SBATCH Preview -->
  <div class="preview-section">
    <div class="preview-header">
      <label>Generated SBATCH Header</label>
      <button 
        class="copy-btn"
        on:click={() => navigator.clipboard.writeText(sbatchPreview)}
      >
        Copy
      </button>
    </div>
    <pre class="sbatch-preview">{sbatchPreview}</pre>
  </div>
</div>

<style>
  .config-panel {
    background: var(--color-bg-primary);
    border-radius: 8px;
    padding: 1.5rem;
    height: 100%;
    overflow-y: auto;
  }
  
  .panel-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1.5rem;
  }
  
  .panel-header h3 {
    margin: 0;
    font-size: 1.125rem;
    color: var(--color-text-primary);
  }
  
  .preview-toggle {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 1rem;
    background: var(--color-bg-secondary);
    border: 1px solid var(--color-border);
    border-radius: 6px;
    color: var(--color-text-primary);
    font-size: 0.875rem;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .preview-toggle:hover {
    background: var(--color-primary);
    color: white;
    border-color: var(--color-primary);
  }
  
  .preview-toggle svg {
    width: 16px;
    height: 16px;
  }
  
  .section {
    margin-bottom: 1.5rem;
  }
  
  .section-label {
    display: block;
    margin-bottom: 0.75rem;
    font-size: 0.875rem;
    font-weight: 600;
    color: var(--color-text-primary);
  }
  
  .section-label.clickable {
    cursor: pointer;
    user-select: none;
  }
  
  .section-label.clickable:hover {
    color: var(--color-primary);
  }
  
  .presets-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.5rem;
  }
  
  .preset-btn {
    padding: 0.5rem;
    background: var(--color-bg-secondary);
    border: 1px solid var(--color-border);
    border-radius: 6px;
    color: var(--color-text-primary);
    font-size: 0.75rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .preset-btn:hover {
    background: var(--color-primary);
    color: white;
    border-color: var(--color-primary);
  }
  
  .form-group {
    margin-bottom: 1rem;
  }
  
  .form-group label {
    display: block;
    margin-bottom: 0.375rem;
    font-size: 0.8125rem;
    color: var(--color-text-secondary);
  }
  
  .form-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1rem;
  }
  
  input[type="text"],
  input[type="number"],
  select {
    width: 100%;
    padding: 0.5rem;
    background: var(--color-bg-secondary);
    border: 1px solid var(--color-border);
    border-radius: 6px;
    color: var(--color-text-primary);
    font-size: 0.875rem;
  }
  
  input:focus,
  select:focus {
    outline: none;
    border-color: var(--color-primary);
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }
  
  input.has-error {
    border-color: var(--color-error);
  }
  
  input.has-warning {
    border-color: var(--color-warning);
  }
  
  .input-with-slider {
    display: flex;
    gap: 0.75rem;
    align-items: center;
  }
  
  .input-with-slider input[type="number"] {
    width: 80px;
  }
  
  .slider {
    flex: 1;
    height: 4px;
    background: var(--color-bg-secondary);
    border-radius: 2px;
    outline: none;
    -webkit-appearance: none;
  }
  
  .slider::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 16px;
    height: 16px;
    background: var(--color-primary);
    border-radius: 50%;
    cursor: pointer;
  }
  
  .slider::-moz-range-thumb {
    width: 16px;
    height: 16px;
    background: var(--color-primary);
    border-radius: 50%;
    cursor: pointer;
    border: none;
  }
  
  .time-input {
    display: flex;
    gap: 0.75rem;
    align-items: center;
  }
  
  .time-input input {
    width: 100px;
  }
  
  .time-display {
    padding: 0.5rem 0.75rem;
    background: var(--color-bg-secondary);
    border-radius: 6px;
    font-family: monospace;
    font-size: 0.875rem;
    color: var(--color-text-secondary);
  }
  
  .error,
  .warning {
    font-size: 0.75rem;
    margin-left: 0.5rem;
  }
  
  .error {
    color: var(--color-error);
  }
  
  .warning {
    color: var(--color-warning);
  }
  
  details {
    border: 1px solid var(--color-border);
    border-radius: 6px;
    padding: 1rem;
  }
  
  details[open] {
    background: var(--color-bg-secondary);
  }
  
  details summary {
    margin: -1rem;
    padding: 1rem;
    cursor: pointer;
  }
  
  details[open] summary {
    margin-bottom: 1rem;
    border-bottom: 1px solid var(--color-border);
  }
  
  .preview-section {
    background: var(--color-bg-secondary);
    border-radius: 6px;
    overflow: hidden;
  }
  
  .preview-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.75rem 1rem;
    background: var(--color-bg-primary);
    border-bottom: 1px solid var(--color-border);
  }
  
  .preview-header label {
    font-size: 0.8125rem;
    font-weight: 600;
    color: var(--color-text-primary);
  }
  
  .copy-btn {
    padding: 0.25rem 0.75rem;
    background: var(--color-primary);
    border: none;
    border-radius: 4px;
    color: white;
    font-size: 0.75rem;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .copy-btn:hover {
    background: var(--color-primary-dark);
  }
  
  .sbatch-preview {
    margin: 0;
    padding: 1rem;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem;
    line-height: 1.5;
    color: var(--color-text-primary);
    overflow-x: auto;
  }
  
  @media (max-width: 768px) {
    .presets-grid {
      grid-template-columns: repeat(2, 1fr);
    }
    
    .form-row {
      grid-template-columns: 1fr;
    }
  }
</style>