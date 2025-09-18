<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { jobParameters } from '../stores/jobParameters';
  import type { SyncMode } from '../stores/jobParameters';

  const dispatch = createEventDispatcher<{
    modeChanged: { mode: SyncMode };
  }>();

  let currentMode: SyncMode = 'bidirectional';

  // Subscribe to the store's sync mode
  $: currentMode = $jobParameters.syncMode;

  function handleModeChange(event: Event) {
    const target = event.target as HTMLSelectElement;
    const mode = target.value as SyncMode;
    jobParameters.setSyncMode(mode);
    dispatch('modeChanged', { mode });
  }

  const syncModes: { value: SyncMode; label: string; description: string }[] = [
    { value: 'bidirectional', label: 'Bidirectional', description: 'Script ↔ Form' },
    { value: 'toForm', label: 'Script → Form', description: 'Script updates form' },
    { value: 'toScript', label: 'Form → Script', description: 'Form updates script' },
    { value: 'off', label: 'Off', description: 'No sync' }
  ];
</script>

<div class="sync-mode-selector">
  <label for="sync-mode" class="sync-label">
    <svg class="sync-icon" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12,18A6,6 0 0,1 6,12C6,11 6.25,10.03 6.7,9.2L5.24,7.74C4.46,8.97 4,10.43 4,12A8,8 0 0,0 12,20V23L16,19L12,15M12,4V1L8,5L12,9V6A6,6 0 0,1 18,12C18,13 17.75,13.97 17.3,14.8L18.76,16.26C19.54,15.03 20,13.57 20,12A8,8 0 0,0 12,4Z"/>
    </svg>
    Sync:
  </label>
  <select
    id="sync-mode"
    class="sync-select"
    value={currentMode}
    on:change={handleModeChange}
  >
    {#each syncModes as mode}
      <option value={mode.value} title={mode.description}>
        {mode.label}
      </option>
    {/each}
  </select>
</div>

<style>
  .sync-mode-selector {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 0.75rem;
    background: linear-gradient(135deg, #f0f4f8 0%, #e8ecf1 100%);
    border: 1px solid #d1d5db;
    border-radius: 8px;
    margin-bottom: 0.75rem;
  }

  .sync-label {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    font-size: 0.875rem;
    font-weight: 500;
    color: #374151;
  }

  .sync-icon {
    width: 1rem;
    height: 1rem;
    color: #6b7280;
  }

  .sync-select {
    flex: 1;
    padding: 0.375rem 0.5rem;
    font-size: 0.875rem;
    background: white;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    color: #1f2937;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .sync-select:focus {
    outline: none;
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  .sync-select:hover {
    background: #f9fafb;
    border-color: #9ca3af;
  }

  /* Mobile adjustments */
  @media (max-width: 768px) {
    .sync-mode-selector {
      padding: 0.625rem;
      margin-bottom: 0.5rem;
    }

    .sync-label {
      font-size: 0.8rem;
    }

    .sync-select {
      font-size: 0.8rem;
      padding: 0.3rem 0.4rem;
    }
  }
</style>