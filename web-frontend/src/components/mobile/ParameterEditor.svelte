<script lang="ts">
  import { run } from 'svelte/legacy';

  import { createEventDispatcher } from 'svelte';
  
  interface Props {
    script?: string;
  }

  let { script = $bindable('') }: Props = $props();
  
  const dispatch = createEventDispatcher<{
    update: { script: string };
  }>();
  
  interface Parameter {
    key: string;
    value: string;
    label: string;
    type: 'text' | 'number' | 'time' | 'memory' | 'select';
    options?: string[];
    min?: number;
    max?: number;
    step?: number;
    unit?: string;
  }
  
  let parameters: Parameter[] = $state([]);
  let customParameters: Parameter[] = $state([]);
  
  // Parse SBATCH parameters from script
  function parseParameters(): void {
    const params: Parameter[] = [];
    const lines = script.split('\n');
    
    lines.forEach(line => {
      if (line.startsWith('#SBATCH')) {
        const match = line.match(/#SBATCH\s+(--?\S+)(?:=(\S+))?/);
        if (match) {
          const [, flag, value = ''] = match;
          const param = createParameter(flag, value);
          if (param) params.push(param);
        }
      }
    });
    
    parameters = params;
  }
  
  function createParameter(flag: string, value: string): Parameter | null {
    switch (flag) {
      case '--job-name':
      case '-J':
        return {
          key: flag,
          value,
          label: 'Job Name',
          type: 'text'
        };
        
      case '--time':
      case '-t':
        return {
          key: flag,
          value,
          label: 'Time Limit',
          type: 'time'
        };
        
      case '--mem':
        return {
          key: flag,
          value: value.replace(/[GMK]/, ''),
          label: 'Memory',
          type: 'memory',
          unit: value.match(/[GMK]/)?.[0] || 'G'
        };
        
      case '--cpus-per-task':
      case '-c':
        return {
          key: flag,
          value: value,
          label: 'CPUs',
          type: 'number',
          min: 1,
          max: 128,
          step: 1
        };
        
      case '--ntasks':
      case '-n':
        return {
          key: flag,
          value: value,
          label: 'Tasks',
          type: 'number',
          min: 1,
          max: 1000,
          step: 1
        };
        
      case '--partition':
      case '-p':
        return {
          key: flag,
          value,
          label: 'Partition',
          type: 'select',
          options: ['gpu', 'cpu', 'bigmem', 'debug', 'normal']
        };
        
      case '--gres':
        const gpuMatch = value.match(/gpu:(\d+)/);
        if (gpuMatch) {
          return {
            key: flag,
            value: gpuMatch[1],
            label: 'GPUs',
            type: 'number',
            min: 0,
            max: 8,
            step: 1
          };
        }
        break;
        
      case '--account':
      case '-A':
        return {
          key: flag,
          value,
          label: 'Account',
          type: 'text'
        };
        
      case '--output':
      case '-o':
        return {
          key: flag,
          value,
          label: 'Output File',
          type: 'text'
        };
        
      case '--error':
      case '-e':
        return {
          key: flag,
          value,
          label: 'Error File',
          type: 'text'
        };
    }
    
    return null;
  }
  
  function updateParameter(param: Parameter): void {
    let newScript = script;
    const lines = newScript.split('\n');
    let updated = false;
    
    for (let i = 0; i < lines.length; i++) {
      if (lines[i].includes(`#SBATCH ${param.key}`)) {
        let newValue = param.value;
        
        // Add unit back for memory
        if (param.type === 'memory' && param.unit) {
          newValue = param.value + param.unit;
        }
        
        // Format GPU parameter
        if (param.label === 'GPUs') {
          newValue = `gpu:${param.value}`;
        }
        
        lines[i] = `#SBATCH ${param.key}=${newValue}`;
        updated = true;
        break;
      }
    }
    
    if (updated) {
      newScript = lines.join('\n');
      script = newScript;
      dispatch('update', { script: newScript });
    }
  }
  
  function formatTime(value: string): { hours: number; minutes: number } {
    const parts = value.split(':');
    if (parts.length === 3) {
      return { hours: parseInt(parts[0]), minutes: parseInt(parts[1]) };
    } else if (parts.length === 2) {
      return { hours: parseInt(parts[0]), minutes: parseInt(parts[1]) };
    }
    return { hours: 1, minutes: 0 };
  }
  
  function updateTime(param: Parameter, hours: number, minutes: number): void {
    param.value = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:00`;
    updateParameter(param);
  }
  
  function addCustomParameter(): void {
    customParameters = [...customParameters, {
      key: '--custom',
      value: '',
      label: 'Custom Parameter',
      type: 'text'
    }];
  }
  
  // Initialize on mount
  run(() => {
    if (script) {
      parseParameters();
    }
  });
  
  // Common quick values
  const quickTimes = ['00:30:00', '01:00:00', '02:00:00', '04:00:00', '08:00:00', '24:00:00'];
  const quickMemory = ['4G', '8G', '16G', '32G', '64G', '128G'];
  const quickCPUs = [1, 2, 4, 8, 16, 32];
</script>

<div class="parameter-editor">
  <div class="editor-header">
    <h3>Quick Settings</h3>
    <button class="add-btn" onclick={addCustomParameter}>
      <svg viewBox="0 0 24 24">
        <path d="M19,13H13V19H11V13H5V11H11V5H13V11H19V13Z" />
      </svg>
      Add
    </button>
  </div>
  
  <div class="parameters-grid">
    {#each parameters as param}
      <div class="parameter-card">
        <label class="param-label">{param.label}</label>
        
        {#if param.type === 'text'}
          <input 
            type="text" 
            bind:value={param.value}
            onchange={() => updateParameter(param)}
            class="param-input"
            placeholder="Enter {param.label.toLowerCase()}"
          />
          
        {:else if param.type === 'number'}
          <div class="number-input">
            <button 
              class="stepper minus" 
              onclick={() => {
                const val = parseInt(param.value) || 0;
                param.value = String(Math.max(param.min || 0, val - (param.step || 1)));
                updateParameter(param);
              }}
            >
              −
            </button>
            <input 
              type="number" 
              bind:value={param.value}
              onchange={() => updateParameter(param)}
              min={param.min}
              max={param.max}
              step={param.step}
              class="param-number"
            />
            <button 
              class="stepper plus" 
              onclick={() => {
                const val = parseInt(param.value) || 0;
                param.value = String(Math.min(param.max || 999, val + (param.step || 1)));
                updateParameter(param);
              }}
            >
              +
            </button>
          </div>
          
          {#if param.label === 'CPUs'}
            <div class="quick-values">
              {#each quickCPUs as cpu}
                <button 
                  class="quick-btn"
                  class:active={param.value === String(cpu)}
                  onclick={() => {
                    param.value = String(cpu);
                    updateParameter(param);
                  }}
                >
                  {cpu}
                </button>
              {/each}
            </div>
          {/if}
          
        {:else if param.type === 'time'}
          {@const time = formatTime(param.value)}
          <div class="time-input">
            <div class="time-group">
              <input 
                type="number" 
                value={time.hours}
                onchange={(e) => updateTime(param, parseInt(e.currentTarget.value) || 0, time.minutes)}
                min="0"
                max="72"
                class="time-field"
              />
              <span class="time-label">hours</span>
            </div>
            <span class="time-separator">:</span>
            <div class="time-group">
              <input 
                type="number" 
                value={time.minutes}
                onchange={(e) => updateTime(param, time.hours, parseInt(e.currentTarget.value) || 0)}
                min="0"
                max="59"
                class="time-field"
              />
              <span class="time-label">mins</span>
            </div>
          </div>
          
          <div class="quick-values">
            {#each quickTimes as qtime}
              <button 
                class="quick-btn"
                class:active={param.value === qtime}
                onclick={() => {
                  param.value = qtime;
                  updateParameter(param);
                }}
              >
                {qtime.replace(':00:00', 'h').replace(':00', '')}
              </button>
            {/each}
          </div>
          
        {:else if param.type === 'memory'}
          <div class="memory-input">
            <input 
              type="number" 
              bind:value={param.value}
              onchange={() => updateParameter(param)}
              min="1"
              max="999"
              class="param-number"
            />
            <select 
              bind:value={param.unit}
              onchange={() => updateParameter(param)}
              class="unit-select"
            >
              <option value="G">GB</option>
              <option value="M">MB</option>
            </select>
          </div>
          
          <div class="quick-values">
            {#each quickMemory as mem}
              <button 
                class="quick-btn"
                class:active={param.value + param.unit === mem}
                onclick={() => {
                  param.value = mem.replace(/[GM]/, '');
                  param.unit = mem.match(/[GM]/)?.[0];
                  updateParameter(param);
                }}
              >
                {mem}
              </button>
            {/each}
          </div>
          
        {:else if param.type === 'select'}
          <select 
            bind:value={param.value}
            onchange={() => updateParameter(param)}
            class="param-select"
          >
            <option value="">Select {param.label}</option>
            {#each param.options || [] as option}
              <option value={option}>{option}</option>
            {/each}
          </select>
        {/if}
      </div>
    {/each}
    
    {#each customParameters as param, i}
      <div class="parameter-card custom">
        <input 
          type="text" 
          bind:value={param.label}
          placeholder="Parameter name"
          class="param-label-input"
        />
        <input 
          type="text" 
          bind:value={param.value}
          placeholder="Value"
          class="param-input"
        />
        <button 
          class="remove-btn"
          onclick={() => customParameters = customParameters.filter((_, idx) => idx !== i)}
        >
          <svg viewBox="0 0 24 24">
            <path d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z" />
          </svg>
        </button>
      </div>
    {/each}
  </div>
</div>

<style>
  .parameter-editor {
    background: #1a1f2e;
    border-radius: 12px;
    padding: 1rem;
  }
  
  .editor-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
  }
  
  .editor-header h3 {
    margin: 0;
    color: #e4e8f1;
    font-size: 1.1rem;
    font-weight: 600;
  }
  
  .add-btn {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.5rem 0.75rem;
    background: #2a3142;
    border: none;
    border-radius: 8px;
    color: #9ca3af;
    font-size: 0.875rem;
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
  }
  
  .add-btn svg {
    width: 16px;
    height: 16px;
  }
  
  .parameters-grid {
    display: grid;
    gap: 1rem;
  }
  
  .parameter-card {
    background: #141925;
    border: 1px solid #2a3142;
    border-radius: 10px;
    padding: 0.875rem;
  }
  
  .parameter-card.custom {
    display: grid;
    grid-template-columns: 1fr 2fr auto;
    gap: 0.5rem;
    align-items: center;
  }
  
  .param-label {
    display: block;
    color: #9ca3af;
    font-size: 0.8rem;
    font-weight: 500;
    margin-bottom: 0.5rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  
  .param-label-input {
    padding: 0.5rem;
    background: #1e2433;
    border: 1px solid #2a3142;
    border-radius: 6px;
    color: #e4e8f1;
    font-size: 0.875rem;
  }
  
  .param-input {
    width: 100%;
    padding: 0.75rem;
    background: #1e2433;
    border: 1px solid #2a3142;
    border-radius: 8px;
    color: #e4e8f1;
    font-size: 1rem;
    outline: none;
  }
  
  .param-input:focus {
    border-color: #3b82f6;
  }
  
  .param-select {
    width: 100%;
    padding: 0.75rem;
    background: #1e2433;
    border: 1px solid #2a3142;
    border-radius: 8px;
    color: #e4e8f1;
    font-size: 1rem;
    outline: none;
    cursor: pointer;
  }
  
  .number-input {
    display: flex;
    align-items: center;
    background: #1e2433;
    border: 1px solid #2a3142;
    border-radius: 8px;
    overflow: hidden;
  }
  
  .stepper {
    width: 44px;
    height: 44px;
    background: transparent;
    border: none;
    color: #9ca3af;
    font-size: 1.5rem;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    -webkit-tap-highlight-color: transparent;
  }
  
  .stepper:active {
    background: #2a3142;
  }
  
  .param-number {
    flex: 1;
    padding: 0.75rem;
    background: transparent;
    border: none;
    color: #e4e8f1;
    font-size: 1.1rem;
    text-align: center;
    outline: none;
  }
  
  .time-input {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  
  .time-group {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
  }
  
  .time-field {
    width: 100%;
    padding: 0.75rem;
    background: #1e2433;
    border: 1px solid #2a3142;
    border-radius: 8px;
    color: #e4e8f1;
    font-size: 1.25rem;
    text-align: center;
    outline: none;
  }
  
  .time-label {
    color: #6b7280;
    font-size: 0.75rem;
    margin-top: 0.25rem;
  }
  
  .time-separator {
    color: #6b7280;
    font-size: 1.5rem;
    margin-bottom: 1rem;
  }
  
  .memory-input {
    display: flex;
    gap: 0.5rem;
  }
  
  .unit-select {
    width: 80px;
    padding: 0.75rem;
    background: #1e2433;
    border: 1px solid #2a3142;
    border-radius: 8px;
    color: #e4e8f1;
    font-size: 1rem;
    cursor: pointer;
  }
  
  .quick-values {
    display: flex;
    gap: 0.5rem;
    margin-top: 0.75rem;
    flex-wrap: wrap;
  }
  
  .quick-btn {
    padding: 0.5rem 0.75rem;
    background: #1e2433;
    border: 1px solid #2a3142;
    border-radius: 6px;
    color: #9ca3af;
    font-size: 0.875rem;
    cursor: pointer;
    transition: all 0.2s;
    -webkit-tap-highlight-color: transparent;
  }
  
  .quick-btn:active,
  .quick-btn.active {
    background: #3b82f6;
    border-color: #3b82f6;
    color: white;
  }
  
  .remove-btn {
    width: 36px;
    height: 36px;
    background: transparent;
    border: none;
    color: #ef4444;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    -webkit-tap-highlight-color: transparent;
  }
  
  .remove-btn svg {
    width: 20px;
    height: 20px;
  }
</style>