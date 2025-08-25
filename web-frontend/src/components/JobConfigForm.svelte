<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import type { HostInfo } from '../types/api';

  const dispatch = createEventDispatcher<{
    configChanged: {
      selectedHost: string;
      sourceDir: string;
      jobName: string;
      partition: string;
      constraint: string;
      account: string;
      cpus: number;
      useMemory: boolean;
      memory: number;
      timeLimit: number;
      nodes: number;
      ntasksPerNode: number;
      gpusPerNode: number;
      gres: string;
      outputFile: string;
      errorFile: string;
    };
  }>();

  export let hosts: HostInfo[] = [];
  export let selectedHost = '';
  export let sourceDir = '';
  export let jobName = '';
  export let partition = '';
  export let constraint = '';
  export let account = '';
  export let cpus = 1;
  export let useMemory = false;
  export let memory = 4; // GB default when enabled
  export let timeLimit = 60; // minutes
  export let nodes = 1;
  export let ntasksPerNode = 1;
  export let gpusPerNode = 0;
  export let gres = '';
  export let outputFile = '';
  export let errorFile = '';
  export let loading = false;

  function onHostChanged(newHostName: string): void {
    const host = hosts.find(h => h.hostname === newHostName);
    if (host && host.slurm_defaults) {
      const defaults = host.slurm_defaults;
      if (defaults.partition) partition = defaults.partition;
      if (defaults.account) account = defaults.account;
      if (defaults.constraint) constraint = defaults.constraint;
      if (defaults.cpus) cpus = defaults.cpus;
      if (defaults.time) {
        const timeParts = defaults.time.split(':');
        const hours = parseInt(timeParts[0], 10) || 0;
        const minutes = parseInt(timeParts[1], 10) || 0;
        timeLimit = hours * 60 + minutes;
      }
    }
    dispatchChange();
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

  function dispatchChange(): void {
    dispatch('configChanged', {
      selectedHost,
      sourceDir,
      jobName,
      partition,
      constraint,
      account,
      cpus,
      useMemory,
      memory,
      timeLimit,
      nodes,
      ntasksPerNode,
      gpusPerNode,
      gres,
      outputFile,
      errorFile
    });
  }

  onMount(() => {
    dispatchChange();
    onHostChanged(selectedHost);
  });

  

  
</script>

<div class="job-config-form">
  <!-- Host Selection -->
  <section class="form-section">
    <div class="section-header">
      <h3>Target Host</h3>
      <div class="section-description">Choose the SLURM cluster to run your job on</div>
    </div>
    <div class="field">
      <label for="host">SLURM Host *</label>
      <select id="host" bind:value={selectedHost} required disabled={loading} class="select-input" on:change={() => onHostChanged(selectedHost)}>
        <option value="">Select a host...</option>
        {#if loading}
          <option disabled>Loading hosts...</option>
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
    <div class="section-header">
      <h3>Source Directory</h3>
      <div class="section-description">Local directory to sync to the remote host</div>
    </div>
    <div class="field">
      <label for="source-dir">Local Directory Path *</label>
      <input
        id="source-dir"
        type="text"
        bind:value={sourceDir}
        placeholder="/path/to/your/project"
        required
        class="text-input"
        on:input={dispatchChange}
      />
      <div class="field-help">
        <svg class="info-icon" viewBox="0 0 24 24" fill="currentColor">
          <path d="M11,9H13V7H11M12,20C7.59,20 4,16.41 4,12C4,7.59 7.59,4 12,4C16.41,4 20,7.59 20,12C20,16.41 16.41,20 12,20M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M11,17H13V11H11V17Z"/>
        </svg>
        This directory will be synchronized to the remote host before job execution
      </div>
    </div>
  </section>

  <!-- Basic SLURM Parameters -->
  <section class="form-section">
    <div class="section-header">
      <h3>Basic Configuration</h3>
      <div class="section-description">Job name and SLURM partition settings</div>
    </div>
    <div class="field-group">
      <div class="field">
        <label for="job-name">Job Name</label>
        <input id="job-name" type="text" bind:value={jobName} placeholder="my-job" class="text-input" on:input={dispatchChange} />
      </div>
      <div class="field">
        <label for="partition">Partition</label>
        <input id="partition" type="text" bind:value={partition} placeholder="gpu" class="text-input" on:input={dispatchChange} />
      </div>
    </div>
    
    <div class="field-group">
      <div class="field">
        <label for="constraint">Constraint</label>
        <input id="constraint" type="text" bind:value={constraint} placeholder="gpu" class="text-input" on:input={dispatchChange} />
        <div class="field-help">
          <svg class="info-icon" viewBox="0 0 24 24" fill="currentColor">
            <path d="M11,9H13V7H11M12,20C7.59,20 4,16.41 4,12C4,7.59 7.59,4 12,4C16.41,4 20,7.59 20,12C20,16.41 16.41,20 12,20M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M11,17H13V11H11V17Z"/>
          </svg>
          Node constraints (e.g., "gpu", "bigmem", "intel")
        </div>
      </div>
      <div class="field">
        <label for="account">Account</label>
        <input id="account" type="text" bind:value={account} placeholder="project-123" class="text-input" on:input={dispatchChange} />
        <div class="field-help">
          <svg class="info-icon" viewBox="0 0 24 24" fill="currentColor">
            <path d="M11,9H13V7H11M12,20C7.59,20 4,16.41 4,12C4,7.59 7.59,4 12,4C16.41,4 20,7.59 20,12C20,16.41 16.41,20 12,20M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M11,17H13V11H11V17Z"/>
          </svg>
          SLURM account for billing purposes
        </div>
      </div>
    </div>
  </section>

  <!-- Resource Configuration -->
  <section class="form-section">
    <div class="section-header">
      <h3>Resource Allocation</h3>
      <div class="section-description">CPU, memory, and compute resource settings</div>
    </div>
    
    <div class="field-group">
      <div class="field">
        <label for="cpus">CPUs: <span class="value-display">{cpus}</span></label>
        <input
          id="cpus"
          type="range"
          min="1"
          max="64"
          bind:value={cpus}
          class="slider"
          on:input={dispatchChange}
        />
      </div>
      
      <div class="field">
        <label for="memory">Memory</label>
        <div class="memory-control">
          <label class="checkbox-control">
            <input type="checkbox" bind:checked={useMemory} on:change={dispatchChange} />
            <span>Specify memory limit</span>
          </label>
          {#if useMemory}
            <div class="memory-slider">
              <label for="memory">{formatMemoryLabel(memory)}</label>
              <input id="memory" type="range" min="1" max="512" bind:value={memory} class="slider" on:input={dispatchChange} />
            </div>
          {/if}
        </div>
      </div>
    </div>

    <div class="field-group">
      <div class="field">
        <label for="nodes">Nodes: <span class="value-display">{nodes}</span></label>
        <input
          id="nodes"
          type="range"
          min="1"
          max="16"
          bind:value={nodes}
          class="slider"
          on:input={dispatchChange}
        />
      </div>
      
      <div class="field">
        <label for="ntasks-per-node">Tasks per Node: <span class="value-display">{ntasksPerNode}</span></label>
        <input
          id="ntasks-per-node"
          type="range"
          min="1"
          max="128"
          bind:value={ntasksPerNode}
          class="slider"
          on:input={dispatchChange}
        />
      </div>
    </div>

    <div class="field">
      <label for="time">Time Limit: <span class="value-display">{formatTimeLabel(timeLimit)}</span></label>
      <input
        id="time"
        type="range"
        min="5"
        max="2880"
        step="5"
        bind:value={timeLimit}
        class="slider"
        on:input={dispatchChange}
      />
    </div>
  </section>

  <!-- GPU and Specialized Resources -->
  <section class="form-section">
    <div class="section-header">
      <h3>GPU & Specialized Resources</h3>
      <div class="section-description">Graphics processing and custom resource requirements</div>
    </div>
    
    <div class="field-group">
      <div class="field">
        <label for="gpus-per-node">GPUs per Node: <span class="value-display">{gpusPerNode}</span></label>
        <input
          id="gpus-per-node"
          type="range"
          min="0"
          max="8"
          bind:value={gpusPerNode}
          class="slider"
          on:input={dispatchChange}
        />
      </div>
      
      <div class="field">
        <label for="gres">Generic Resources</label>
        <input id="gres" type="text" bind:value={gres} placeholder="gpu:tesla:2" class="text-input" on:input={dispatchChange} />
        <div class="field-help">
          <svg class="info-icon" viewBox="0 0 24 24" fill="currentColor">
            <path d="M11,9H13V7H11M12,20C7.59,20 4,16.41 4,12C4,7.59 7.59,4 12,4C16.41,4 20,7.59 20,12C20,16.41 16.41,20 12,20M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,1 0 0,0 12,2M11,17H13V11H11V17Z"/>
          </svg>
          Generic resource specification (e.g., "gpu:tesla:2")
        </div>
      </div>
    </div>
  </section>

  <!-- Output Configuration -->
  <section class="form-section">
    <div class="section-header">
      <h3>Output & Environment</h3>
      <div class="section-description">Job output files and environment setup</div>
    </div>
    
    <div class="field-group">
      <div class="field">
        <label for="output">Output File</label>
        <input
          id="output"
          type="text"
          bind:value={outputFile}
          placeholder="job-%j.out"
          class="text-input"
          on:input={dispatchChange}
        />
      </div>
      
      <div class="field">
        <label for="error">Error File</label>
        <input
          id="error"
          type="text"
          bind:value={errorFile}
          placeholder="job-%j.err"
          class="text-input"
          on:input={dispatchChange}
        />
      </div>
    </div>

  </section>
</div>

<style>
  .job-config-form {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
    padding: 1.5rem;
    background: white;
    border-radius: 12px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  }

  .form-section {
    background: #fafbfc;
    border: 1px solid #e1e5e9;
    border-radius: 10px;
    padding: 1.25rem;
    transition: all 0.2s ease;
  }

  .form-section:hover {
    border-color: #c7d2fe;
    box-shadow: 0 2px 8px rgba(99, 102, 241, 0.1);
  }

  .section-header {
    margin-bottom: 1.25rem;
  }

  .section-header h3 {
    margin: 0 0 0.5rem 0;
    color: #374151;
    font-size: 1.125rem;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .section-header h3::before {
    content: '';
    width: 4px;
    height: 20px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 2px;
  }

  .section-description {
    font-size: 0.9rem;
    color: #6b7280;
    line-height: 1.4;
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
    margin-bottom: 1rem;
  }

  .field-group:last-child {
    margin-bottom: 0;
  }

  .field label {
    display: block;
    margin-bottom: 0.5rem;
    font-weight: 500;
    color: #374151;
    font-size: 0.9rem;
  }

  .value-display {
    font-weight: 600;
    color: #667eea;
  }

  .text-input,
  .select-input {
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

  .text-input:focus,
  .select-input:focus {
    outline: none;
    border-color: #667eea;
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1), 0 2px 4px rgba(0, 0, 0, 0.1);
    transform: translateY(-1px);
  }

  .text-input:disabled,
  .select-input:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .field-help {
    margin-top: 0.5rem;
    font-size: 0.8rem;
    color: #6b7280;
    display: flex;
    align-items: flex-start;
    gap: 0.375rem;
    line-height: 1.4;
  }


  .info-icon {
    width: 14px;
    height: 14px;
    flex-shrink: 0;
    margin-top: 0.1rem;
    color: #9ca3af;
  }

  .memory-control {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .checkbox-control {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.9rem;
    color: #374151;
    cursor: pointer;
  }

  .checkbox-control input[type="checkbox"] {
    margin: 0;
    cursor: pointer;
    width: 16px;
    height: 16px;
  }

  .memory-slider {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .slider {
    width: 100%;
    height: 8px;
    border-radius: 4px;
    background: linear-gradient(90deg, #e5e7eb 0%, #f3f4f6 100%);
    outline: none;
    -webkit-appearance: none;
    transition: all 0.2s ease;
    cursor: pointer;
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

  /* Mobile responsive */
  @media (max-width: 768px) {
    .job-config-form {
      padding: 1rem;
      gap: 1.25rem;
    }

    .form-section {
      padding: 1rem;
      border-radius: 8px;
    }

    .section-header {
      margin-bottom: 1rem;
    }

    .section-header h3 {
      font-size: 1rem;
    }

    .section-description {
      font-size: 0.85rem;
    }

    .field-group {
      grid-template-columns: 1fr;
      gap: 0.75rem;
    }

    .field label {
      font-size: 0.85rem;
    }

    .text-input,
    .select-input {
      padding: 0.625rem;
      font-size: 0.85rem;
    }

    .field-help {
      font-size: 0.75rem;
    }


    .memory-control {
      gap: 0.5rem;
    }

    .checkbox-control {
      font-size: 0.85rem;
    }

    .slider {
      height: 12px;
    }

    .slider::-webkit-slider-thumb {
      width: 24px;
      height: 24px;
    }

    .slider::-moz-range-thumb {
      width: 24px;
      height: 24px;
    }
  }

  /* Touch device improvements */
  @media (hover: none) and (pointer: coarse) {
    .checkbox-control input[type="checkbox"] {
      width: 18px;
      height: 18px;
      cursor: pointer;
      touch-action: manipulation;
    }

    .slider {
      height: 12px;
      touch-action: pan-x;
    }

    .slider::-webkit-slider-thumb {
      width: 24px;
      height: 24px;
    }

    .slider::-moz-range-thumb {
      width: 24px;
      height: 24px;
    }

    .text-input,
    .select-input {
      min-height: 48px;
      touch-action: manipulation;
    }
  }
</style>