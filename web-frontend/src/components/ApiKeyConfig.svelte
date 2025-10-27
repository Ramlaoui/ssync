<script lang="ts">
  import { apiConfig, setApiKey, clearApiKey, testConnection } from '../services/api';
  import { onMount } from 'svelte';
  import { push } from 'svelte-spa-router';
  import { ArrowLeft } from 'lucide-svelte';
  
  let showApiKey = $state(false);
  let apiKeyInput = $state('');
  let testing = $state(false);
  let testResult: 'success' | 'error' | null = $state(null);
  
  let isConfigured = $derived($apiConfig.apiKey !== '');
  
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

<div class="settings-page">
  <!-- Navigation Header -->
  <header class="bg-white dark:bg-card border-b border-gray-200 dark:border-border sticky top-0 z-40">
    <div class="px-4 sm:px-6 lg:px-8">
      <div class="flex h-16 items-center">
        <button
          class="flex items-center gap-2 px-3 py-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-secondary rounded-lg font-medium transition-colors"
          onclick={() => push('/')}
        >
          <ArrowLeft class="w-4 h-4" />
          Home
        </button>
        <div class="w-px h-6 bg-gray-300 dark:bg-border mx-4"></div>
        <h1 class="text-lg font-semibold text-gray-900 dark:text-foreground">Settings</h1>
      </div>
    </div>
  </header>

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
            onkeydown={(e) => e.key === 'Enter' && handleSaveApiKey()}
          />
        {:else}
          <input
            type="password"
            placeholder="Enter your API key..."
            bind:value={apiKeyInput}
            onkeydown={(e) => e.key === 'Enter' && handleSaveApiKey()}
          />
        {/if}
        <button
          type="button"
          class="toggle-visibility"
          onclick={toggleShowApiKey}
        >
          {showApiKey ? 'Show' : 'Hide'}
        </button>
        <button
          type="button"
          class="primary"
          onclick={handleSaveApiKey}
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
          onclick={handleTestConnection}
          disabled={testing}
        >
          {testing ? 'Testing...' : 'Test Connection'}
        </button>
        
        <button
          type="button"
          class="danger"
          onclick={handleClearApiKey}
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
</div>

<style>
  .api-key-config {
    background: var(--card);
    border: 1px solid var(--border);
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
    background: var(--secondary);
  }
  
  .status.success {
    background: var(--success-bg);
    color: var(--success);
  }

  .status.warning {
    background: var(--warning-bg);
    color: var(--warning);
  }

  .info {
    color: var(--muted-foreground);
    margin-bottom: 1rem;
  }

  .command {
    background: var(--secondary);
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
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--input);
    color: var(--foreground);
    font-family: var(--font-mono);
  }

  .toggle-visibility {
    padding: 0.5rem;
    background: var(--secondary);
    border: 1px solid var(--border);
    border-radius: 4px;
    cursor: pointer;
  }

  .toggle-visibility:hover {
    background: var(--muted);
  }

  button.primary {
    background: var(--accent);
    color: white;
    border: none;
    padding: 0.5rem 1rem;
    border-radius: 4px;
    cursor: pointer;
    font-weight: 500;
  }

  button.primary:hover:not(:disabled) {
    background: var(--accent);
    opacity: 0.9;
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
    background: var(--secondary);
    border-radius: 4px;
  }

  .key-display label {
    font-weight: 500;
  }

  .key-display code {
    font-family: var(--font-mono);
    color: var(--accent);
  }

  .actions {
    display: flex;
    gap: 0.5rem;
  }

  .actions button {
    padding: 0.5rem 1rem;
    border-radius: 4px;
    border: 1px solid var(--border);
    background: var(--card);
    cursor: pointer;
    transition: background 0.2s;
  }

  .actions button:hover:not(:disabled) {
    background: var(--secondary);
  }

  .actions button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .actions button.danger {
    border-color: var(--error);
    color: var(--error);
  }

  .actions button.danger:hover {
    background: var(--error-bg);
  }

  .message {
    padding: 0.75rem;
    border-radius: 4px;
    font-size: 0.9rem;
  }

  .message.success {
    background: var(--success-bg);
    color: var(--success);
    border: 1px solid var(--success);
  }

  .message.error {
    background: var(--error-bg);
    color: var(--error);
    border: 1px solid var(--error);
  }
</style>