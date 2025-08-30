<script lang="ts">
  import { apiConfig, setApiKey, clearApiKey, testConnection } from '../services/api';
  import { onMount } from 'svelte';
  
  let showApiKey = false;
  let apiKeyInput = '';
  let testing = false;
  let testResult: 'success' | 'error' | null = null;
  
  $: isConfigured = $apiConfig.apiKey !== '';
  
  onMount(async () => {
    if ($apiConfig.apiKey) {
      await handleTestConnection();
    }
  });
  
  async function handleTestConnection() {
    testing = true;
    testResult = null;
    
    const success = await testConnection();
    testResult = success ? 'success' : 'error';
    testing = false;
  }
  
  function handleSaveApiKey() {
    if (apiKeyInput.trim()) {
      setApiKey(apiKeyInput.trim());
      apiKeyInput = '';
      showApiKey = false;
      handleTestConnection();
    }
  }
  
  function handleClearApiKey() {
    if (confirm('Are you sure you want to remove the API key?')) {
      clearApiKey();
      testResult = null;
    }
  }
  
  function toggleShowApiKey() {
    showApiKey = !showApiKey;
  }
</script>

<div class="api-key-config">
  <div class="header">
    <h3>API Authentication</h3>
    {#if $apiConfig.authenticated}
      <span class="status success">Connected</span>
    {:else if isConfigured}
      <span class="status warning">Not authenticated</span>
    {:else}
      <span class="status">Not configured</span>
    {/if}
  </div>
  
  {#if !isConfigured}
    <div class="setup">
      <p class="info">
        To use the API, you need to configure an API key.
        Generate one using the CLI:
      </p>
      <pre class="command">ssync auth setup</pre>
      
      <div class="input-group">
        {#if showApiKey}
          <input
            type="text"
            placeholder="Enter your API key..."
            bind:value={apiKeyInput}
            on:keydown={(e) => e.key === 'Enter' && handleSaveApiKey()}
          />
        {:else}
          <input
            type="password"
            placeholder="Enter your API key..."
            bind:value={apiKeyInput}
            on:keydown={(e) => e.key === 'Enter' && handleSaveApiKey()}
          />
        {/if}
        <button
          type="button"
          class="toggle-visibility"
          on:click={toggleShowApiKey}
        >
          {showApiKey ? 'Show' : 'Hide'}
        </button>
        <button
          type="button"
          class="primary"
          on:click={handleSaveApiKey}
          disabled={!apiKeyInput.trim()}
        >
          Save API Key
        </button>
      </div>
    </div>
  {:else}
    <div class="configured">
      <div class="key-display">
        <span>Current API Key:</span>
        <code>{$apiConfig.apiKey.substring(0, 8)}...{$apiConfig.apiKey.substring($apiConfig.apiKey.length - 4)}</code>
      </div>
      
      <div class="actions">
        <button
          type="button"
          on:click={handleTestConnection}
          disabled={testing}
        >
          {testing ? 'Testing...' : 'Test Connection'}
        </button>
        
        <button
          type="button"
          class="danger"
          on:click={handleClearApiKey}
        >
          Remove API Key
        </button>
      </div>
      
      {#if testResult === 'success'}
        <div class="message success">
          API connection successful!
        </div>
      {:else if testResult === 'error'}
        <div class="message error">
          {$apiConfig.authError || 'Connection failed'}
        </div>
      {/if}
    </div>
  {/if}
  
  {#if $apiConfig.authError && !testResult}
    <div class="message error">
      {$apiConfig.authError}
    </div>
  {/if}
</div>

<style>
  .api-key-config {
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: 8px;
    padding: 1.5rem;
    margin-bottom: 2rem;
  }
  
  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
  }
  
  .header h3 {
    margin: 0;
    font-size: 1.2rem;
  }
  
  .status {
    font-size: 0.9rem;
    padding: 0.25rem 0.75rem;
    border-radius: 12px;
    background: var(--color-surface-2);
  }
  
  .status.success {
    background: var(--color-success-bg);
    color: var(--color-success);
  }
  
  .status.warning {
    background: var(--color-warning-bg);
    color: var(--color-warning);
  }
  
  .info {
    color: var(--color-text-secondary);
    margin-bottom: 1rem;
  }
  
  .command {
    background: var(--color-surface-2);
    padding: 0.75rem;
    border-radius: 4px;
    font-family: var(--font-mono);
    margin-bottom: 1.5rem;
  }
  
  .input-group {
    display: flex;
    gap: 0.5rem;
  }
  
  .input-group input {
    flex: 1;
    padding: 0.5rem;
    border: 1px solid var(--color-border);
    border-radius: 4px;
    background: var(--color-surface);
    color: var(--color-text);
    font-family: var(--font-mono);
  }
  
  .toggle-visibility {
    padding: 0.5rem;
    background: var(--color-surface-2);
    border: 1px solid var(--color-border);
    border-radius: 4px;
    cursor: pointer;
  }
  
  .toggle-visibility:hover {
    background: var(--color-surface-3);
  }
  
  button.primary {
    background: var(--color-primary);
    color: white;
    border: none;
    padding: 0.5rem 1rem;
    border-radius: 4px;
    cursor: pointer;
    font-weight: 500;
  }
  
  button.primary:hover:not(:disabled) {
    background: var(--color-primary-dark);
  }
  
  button.primary:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  
  .configured {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }
  
  .key-display {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 0.75rem;
    background: var(--color-surface-2);
    border-radius: 4px;
  }
  
  .key-display label {
    font-weight: 500;
  }
  
  .key-display code {
    font-family: var(--font-mono);
    color: var(--color-primary);
  }
  
  .actions {
    display: flex;
    gap: 0.5rem;
  }
  
  .actions button {
    padding: 0.5rem 1rem;
    border-radius: 4px;
    border: 1px solid var(--color-border);
    background: var(--color-surface);
    cursor: pointer;
    transition: background 0.2s;
  }
  
  .actions button:hover:not(:disabled) {
    background: var(--color-surface-2);
  }
  
  .actions button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  
  .actions button.danger {
    border-color: var(--color-error);
    color: var(--color-error);
  }
  
  .actions button.danger:hover {
    background: var(--color-error-bg);
  }
  
  .message {
    padding: 0.75rem;
    border-radius: 4px;
    font-size: 0.9rem;
  }
  
  .message.success {
    background: var(--color-success-bg);
    color: var(--color-success);
    border: 1px solid var(--color-success);
  }
  
  .message.error {
    background: var(--color-error-bg);
    color: var(--color-error);
    border: 1px solid var(--color-error);
  }
</style>