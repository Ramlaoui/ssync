<script lang="ts">
  import type { JobParameter } from '../stores/jobParameters';
  
  interface Props {
    parameters: Map<string, JobParameter>;
    scriptHasSbatch?: boolean;
  }

  let { parameters, scriptHasSbatch = false }: Props = $props();
  
  // Count synced parameters
  let scriptParameterCount = $derived(Array.from(parameters.values()).filter(p => p.scriptLine !== undefined).length);
  let enabledParameterCount = $derived(Array.from(parameters.values()).filter(p => p.enabled).length);
</script>

<div class="sync-status-container">
  {#if scriptHasSbatch}
    <div class="sync-header">
      <div class="sync-info">
        <svg class="icon" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12,18A6,6 0 0,1 6,12C6,11 6.25,10.03 6.7,9.2L5.24,7.74C4.46,8.97 4,10.43 4,12A8,8 0 0,0 12,20V23L16,19L12,15M12,4V1L8,5L12,9V6A6,6 0 0,1 18,12C18,13 17.75,13.97 17.3,14.8L18.76,16.26C19.54,15.03 20,13.57 20,12A8,8 0 0,0 12,4Z"/>
        </svg>
        <span class="sync-label">Parameters synced with script</span>
      </div>
      
      <div class="sync-indicators">
        {#if scriptParameterCount > 0}
          <span class="indicator script-params" title="Parameters defined in script">
            <svg class="icon" viewBox="0 0 24 24" fill="currentColor">
              <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z"/>
            </svg>
            {scriptParameterCount} in script
          </span>
        {/if}
        
        {#if enabledParameterCount > 0}
          <span class="indicator synced" title="Active parameters">
            <svg class="icon" viewBox="0 0 24 24" fill="currentColor">
              <path d="M21,7L9,19L3.5,13.5L4.91,12.09L9,16.17L19.59,5.59L21,7Z"/>
            </svg>
            {enabledParameterCount} active
          </span>
        {/if}
      </div>
    </div>
    
  {/if}
</div>

<style>
  .sync-status-container {
    padding: 0.75rem;
    background: var(--surface-2, #f8f9fa);
    border: 1px solid var(--border-color, #e0e0e0);
    border-radius: 6px;
    margin-bottom: 1rem;
  }
  
  .sync-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 1rem;
  }
  
  .sync-info {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  
  .sync-label {
    font-weight: 500;
    color: var(--text-secondary, #666);
    font-size: 0.875rem;
  }
  
  .sync-indicators {
    display: flex;
    gap: 1rem;
    align-items: center;
  }
  
  .indicator {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    font-size: 0.875rem;
    font-weight: 500;
  }
  
  .indicator.script-params {
    background: var(--blue-light, #e3f2fd);
    color: var(--blue-dark, #1565c0);
  }
  
  .indicator.synced {
    background: var(--green-light, #e8f5e9);
    color: var(--green-dark, #2e7d32);
  }
  
  .indicator.conflicts {
    background: var(--orange-light, #fff3e0);
    color: var(--orange-dark, #e65100);
  }
  
  .icon {
    width: 16px;
    height: 16px;
  }
  
  .conflict-section {
    margin-top: 1rem;
    padding-top: 1rem;
    border-top: 1px solid var(--border-color, #e0e0e0);
  }
  
  .conflict-toggle {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    width: 100%;
    padding: 0.5rem;
    background: var(--orange-light, #fff3e0);
    border: 1px solid var(--orange-border, #ffcc80);
    border-radius: 4px;
    color: var(--orange-dark, #e65100);
    font-weight: 500;
    cursor: pointer;
    transition: background-color 0.2s;
  }
  
  .conflict-toggle:hover {
    background: var(--orange-hover, #ffe0b2);
  }
  
  .chevron {
    transition: transform 0.2s;
  }
  
  .chevron.rotated {
    transform: rotate(180deg);
  }
  
  .conflict-details {
    margin-top: 0.75rem;
    padding: 0.75rem;
    background: white;
    border: 1px solid var(--border-color, #e0e0e0);
    border-radius: 4px;
  }
  
  .conflict-list {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  
  .conflict-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.5rem;
    background: var(--surface-1, #fafafa);
    border-radius: 4px;
  }
  
  .param-name {
    font-weight: 500;
    color: var(--text-primary, #333);
  }
  
  .conflict-values {
    display: flex;
    gap: 1.5rem;
  }
  
  .value-item {
    display: flex;
    gap: 0.25rem;
    align-items: center;
  }
  
  .value-label {
    font-size: 0.75rem;
    color: var(--text-secondary, #666);
    text-transform: uppercase;
  }
  
  .value-content {
    font-family: 'Monaco', 'Menlo', monospace;
    font-size: 0.875rem;
    padding: 0.125rem 0.25rem;
    background: white;
    border: 1px solid var(--border-color, #ddd);
    border-radius: 2px;
  }
  
  .resolution-options {
    margin-top: 1rem;
    padding-top: 1rem;
    border-top: 1px solid var(--border-color, #e0e0e0);
  }
  
  .resolution-label {
    font-size: 0.875rem;
    color: var(--text-secondary, #666);
    margin-bottom: 0.5rem;
  }
  
  .resolution-buttons {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
  }
  
  .resolution-btn {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.375rem 0.75rem;
    border: 1px solid var(--border-color, #ddd);
    border-radius: 4px;
    background: white;
    font-size: 0.875rem;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .resolution-btn:hover {
    background: var(--surface-1, #fafafa);
    border-color: var(--primary, #4a90e2);
    color: var(--primary, #4a90e2);
  }
  
  .resolution-btn.use-script {
    border-color: var(--blue-border, #90caf9);
  }
  
  .resolution-btn.use-form {
    border-color: var(--green-border, #a5d6a7);
  }
  
  .resolution-btn.merge {
    border-color: var(--purple-border, #ce93d8);
  }
  
  .no-sbatch-notice {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem;
    background: var(--info-light, #e3f2fd);
    border-radius: 4px;
    color: var(--info-dark, #1565c0);
    font-size: 0.875rem;
  }
  
  .icon.info {
    color: var(--info-dark, #1565c0);
  }
  
  @media (max-width: 768px) {
    .sync-header {
      flex-direction: column;
      align-items: flex-start;
    }
    
    .conflict-values {
      flex-direction: column;
      gap: 0.25rem;
    }
    
    .resolution-buttons {
      flex-direction: column;
    }
    
    .resolution-btn {
      width: 100%;
      justify-content: center;
    }
  }
</style>