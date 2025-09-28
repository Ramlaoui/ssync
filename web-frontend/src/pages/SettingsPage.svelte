<script lang="ts">
  import { onMount } from 'svelte';
  import { push } from 'svelte-spa-router';
  import NavigationHeader from '../components/NavigationHeader.svelte';
  import SyncSettings from '../components/SyncSettings.svelte';
  import { apiConfig, setApiKey, clearApiKey, testConnection } from '../services/api';
  import {
    Key,
    Eye,
    EyeOff,
    Check,
    X,
    RefreshCw,
    Moon,
    Sun,
    Bell,
    Database,
    Shield,
    Monitor,
    Zap,
    Trash2,
    Download,
    Upload,
    ChevronRight,
    Settings as SettingsIcon
  } from 'lucide-svelte';

  // Mobile detection
  let isMobile = typeof window !== 'undefined' && window.innerWidth < 768;

  // API Key state
  let showApiKey = false;
  let apiKeyInput = '';
  let testing = false;
  let testResult: 'success' | 'error' | null = null;

  // UI Preferences (stored in localStorage)
  let preferences = {
    theme: 'light',
    autoRefresh: false,
    refreshInterval: 30,
    compactMode: false,
    showNotifications: false,
    soundAlerts: false,
    jobsPerPage: 50,
    defaultJobView: 'table',
    showCompletedJobs: true,
    groupJobsByHost: false
  };

  // Auto-refresh timer
  let refreshTimer: number | null = null;

  // Cache stats
  let cacheStats = {
    size: '0 MB',
    entries: 0,
    lastCleared: null as Date | null
  };
  let loadingCacheStats = false;
  let clearingCache = false;

  // Active section for mobile
  let activeSection: string | null = null;

  // Collapsible sections state - expand on mobile when viewing sync section
  $: collapsedSections = {
    sync: !(isMobile && activeSection === 'sync') // Expand on mobile when viewing sync section
  };

  $: isConfigured = $apiConfig.apiKey !== '';

  function checkMobile() {
    isMobile = window.innerWidth < 768;
  }

  onMount(() => {
    checkMobile();
    window.addEventListener('resize', checkMobile);

    // Load preferences from localStorage
    loadPreferences();

    // Apply theme on mount
    if (preferences.theme === 'dark') {
      document.documentElement.setAttribute('data-theme', 'dark');
    } else {
      document.documentElement.setAttribute('data-theme', 'light');
    }

    // Apply compact mode if enabled
    if (preferences.compactMode) {
      document.documentElement.classList.add('compact-mode');
    }

    // Test connection if API key exists
    if ($apiConfig.apiKey) {
      handleTestConnection();
    }

    // Load cache stats
    loadCacheStats();

    return () => {
      window.removeEventListener('resize', checkMobile);
    };
  });

  function loadPreferences() {
    const saved = localStorage.getItem('ssync_preferences');
    if (saved) {
      try {
        preferences = { ...preferences, ...JSON.parse(saved) };
      } catch (e) {
        console.error('Failed to load preferences:', e);
      }
    }
  }

  function savePreferences() {
    localStorage.setItem('ssync_preferences', JSON.stringify(preferences));
  }

  async function handlePreferenceChange(key: string, value: any) {
    preferences[key] = value;
    savePreferences();

    // Apply changes immediately
    if (key === 'theme') {
      document.documentElement.setAttribute('data-theme', value);
    } else if (key === 'compactMode') {
      document.documentElement.classList.toggle('compact-mode', value);
    } else if (key === 'autoRefresh' || key === 'refreshInterval') {
      // Broadcast preference change to other components
      window.dispatchEvent(new CustomEvent('autoRefreshSettingsChanged', {
        detail: {
          enabled: preferences.autoRefresh,
          interval: preferences.refreshInterval
        }
      }));
    } else if (key === 'showNotifications' && value) {
      // Request notification permission if enabling
      if ('Notification' in window && Notification.permission === 'default') {
        const permission = await Notification.requestPermission();
        if (permission !== 'granted') {
          preferences.showNotifications = false;
          savePreferences();
        }
      }
    }

    // Broadcast notification settings changes
    if (key === 'showNotifications' || key === 'soundAlerts') {
      window.dispatchEvent(new CustomEvent('notificationSettingsChanged', {
        detail: {
          showNotifications: preferences.showNotifications,
          soundAlerts: preferences.soundAlerts
        }
      }));
    }

    // Broadcast jobs per page change
    if (key === 'jobsPerPage') {
      window.dispatchEvent(new CustomEvent('jobsPerPageChanged', {
        detail: {
          jobsPerPage: preferences.jobsPerPage
        }
      }));
    }
  }

  async function loadCacheStats() {
    loadingCacheStats = true;
    try {
      const response = await fetch('/api/cache/stats', {
        headers: {
          'X-API-Key': $apiConfig.apiKey || ''
        }
      });

      if (response.ok) {
        const data = await response.json();
        const stats = data.statistics;

        // Get size in MB (already calculated by backend)
        const sizeMB = (stats.db_size_mb || 0).toFixed(1);

        // Calculate total entries
        const totalEntries = (stats.total_jobs || 0) + (stats.date_range_cache?.active_ranges || 0);

        cacheStats = {
          size: `${sizeMB} MB`,
          entries: totalEntries,
          lastCleared: stats.oldest_entry ? new Date(stats.oldest_entry) : null
        };
      }
    } catch (error) {
      console.error('Failed to load cache stats:', error);
    } finally {
      loadingCacheStats = false;
    }
  }

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

  async function clearCache() {
    if (confirm('Are you sure you want to clear all cached data? This cannot be undone.')) {
      clearingCache = true;
      try {
        const response = await fetch('/api/cache/clear', {
          method: 'POST',
          headers: {
            'X-API-Key': $apiConfig.apiKey || ''
          }
        });

        if (response.ok) {
          // Reload cache stats after clearing
          await loadCacheStats();
        } else {
          console.error('Failed to clear cache');
        }
      } catch (error) {
        console.error('Error clearing cache:', error);
      } finally {
        clearingCache = false;
      }
    }
  }

  function exportSettings() {
    const data = {
      preferences,
      apiKey: $apiConfig.apiKey ? '***' : null,
      exportDate: new Date().toISOString()
    };

    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ssync-settings-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function importSettings() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (file) {
        const text = await file.text();
        try {
          const data = JSON.parse(text);
          if (data.preferences) {
            preferences = { ...preferences, ...data.preferences };
            savePreferences();
          }
        } catch (e) {
          console.error('Failed to import settings:', e);
        }
      }
    };
    input.click();
  }

  function getSectionTitle(section: string): string {
    const titles = {
      'api': 'API Authentication',
      'display': 'Display Preferences',
      'sync': 'Sync Settings',
      'notifications': 'Notifications',
      'cache': 'Cache Management',
      'data': 'Data & Privacy'
    };
    return titles[section] || 'Settings';
  }
</script>

<div class="h-full flex flex-col bg-white">
  {#if !isMobile || activeSection !== null}
    <NavigationHeader
      title={isMobile && activeSection ? getSectionTitle(activeSection) : "Settings"}
      showBackButton={true}
      customBackHandler={isMobile && activeSection !== null}
      customBackLabel={isMobile && activeSection ? "Settings" : ""}
      on:back={() => activeSection = null}
    />
  {/if}

  <div class="flex-1 overflow-auto">
    {#if isMobile && !activeSection}
      <!-- Mobile: Settings list -->
      <div>
        <button
          class="flex items-center w-full p-4 bg-white border-0 border-b border-gray-200 cursor-pointer transition-colors hover:bg-gray-50 text-left"
          on:click={() => activeSection = 'api'}
        >
          <div class="flex items-center justify-center w-10 h-10 bg-gray-100 rounded-[10px] mr-4">
            <Key class="w-5 h-5" />
          </div>
          <div class="flex-1">
            <div class="font-medium text-gray-900 mb-1">API Authentication</div>
            <div class="text-sm text-gray-500">
              {#if $apiConfig.authenticated}
                <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-emerald-100 text-emerald-800">Connected</span>
              {:else if isConfigured}
                <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-amber-100 text-amber-800">Not authenticated</span>
              {:else}
                <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-600">Not configured</span>
              {/if}
            </div>
          </div>
          <ChevronRight class="w-4 h-4 text-gray-400" />
        </button>

        <button
          class="flex items-center w-full p-4 bg-white border-0 border-b border-gray-200 cursor-pointer transition-colors hover:bg-gray-50 text-left"
          on:click={() => activeSection = 'display'}
        >
          <div class="flex items-center justify-center w-10 h-10 bg-gray-100 rounded-[10px] mr-4">
            <Monitor class="w-5 h-5" />
          </div>
          <div class="flex-1">
            <div class="font-medium text-gray-900 mb-1">Display Preferences</div>
            <div class="text-sm text-gray-500">Theme, layout, and appearance</div>
          </div>
          <ChevronRight class="w-4 h-4 text-gray-400" />
        </button>

        <button
          class="flex items-center w-full p-4 bg-white border-0 border-b border-gray-200 cursor-pointer transition-colors hover:bg-gray-50 text-left"
          on:click={() => activeSection = 'sync'}
        >
          <div class="flex items-center justify-center w-10 h-10 bg-gray-100 rounded-[10px] mr-4">
            <RefreshCw class="w-5 h-5" />
          </div>
          <div class="flex-1">
            <div class="font-medium text-gray-900 mb-1">Sync Settings</div>
            <div class="text-sm text-gray-500">File patterns and filters</div>
          </div>
          <ChevronRight class="w-4 h-4 text-gray-400" />
        </button>

        <button
          class="flex items-center w-full p-4 bg-white border-0 border-b border-gray-200 cursor-pointer transition-colors hover:bg-gray-50 text-left"
          on:click={() => activeSection = 'notifications'}
        >
          <div class="flex items-center justify-center w-10 h-10 bg-gray-100 rounded-[10px] mr-4">
            <Bell class="w-5 h-5" />
          </div>
          <div class="flex-1">
            <div class="font-medium text-gray-900 mb-1">Notifications</div>
            <div class="text-sm text-gray-500">Alerts and sounds</div>
          </div>
          <ChevronRight class="w-4 h-4 text-gray-400" />
        </button>

        <button
          class="flex items-center w-full p-4 bg-white border-0 border-b border-gray-200 cursor-pointer transition-colors hover:bg-gray-50 text-left"
          on:click={() => activeSection = 'cache'}
        >
          <div class="flex items-center justify-center w-10 h-10 bg-gray-100 rounded-[10px] mr-4">
            <Database class="w-5 h-5" />
          </div>
          <div class="flex-1">
            <div class="font-medium text-gray-900 mb-1">Cache Management</div>
            <div class="text-sm text-gray-500">{cacheStats.size} used</div>
          </div>
          <ChevronRight class="w-4 h-4 text-gray-400" />
        </button>

        <button
          class="flex items-center w-full p-4 bg-white border-0 border-b border-gray-200 cursor-pointer transition-colors hover:bg-gray-50 text-left"
          on:click={() => activeSection = 'data'}
        >
          <div class="flex items-center justify-center w-10 h-10 bg-gray-100 rounded-[10px] mr-4">
            <Shield class="w-5 h-5" />
          </div>
          <div class="flex-1">
            <div class="font-medium text-gray-900 mb-1">Data & Privacy</div>
            <div class="text-sm text-gray-500">Export and import settings</div>
          </div>
          <ChevronRight class="w-4 h-4 text-gray-400" />
        </button>
      </div>
    {:else}
      <!-- Desktop: Grid layout / Mobile: Section view -->
      <div class="p-4 grid gap-4 lg:grid-cols-2 xl:grid-cols-3 {isMobile ? 'grid-cols-1' : ''}">
        {#if !isMobile || activeSection === 'api'}
          <!-- API Authentication Section -->
          <div class="bg-white border border-gray-200 rounded-xl p-6 {activeSection === 'sync' ? 'lg:col-span-2 xl:col-span-3' : ''}">
            <div class="flex justify-between items-center mb-6 pb-4 border-b border-gray-100">
              <div class="flex items-center gap-3">
                <Key class="w-5 h-5" />
                <h2 class="text-lg font-semibold text-gray-900 m-0">API Authentication</h2>
              </div>
              {#if $apiConfig.authenticated}
                <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-emerald-100 text-emerald-800">Connected</span>
              {:else if isConfigured}
                <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-amber-100 text-amber-800">Not authenticated</span>
              {:else}
                <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-600">Not configured</span>
              {/if}
            </div>

            <div class="section-content">
              {#if !isConfigured}
                <div class="help-text">
                  To use the API, generate a key using the CLI:
                </div>
                <pre class="command">ssync auth setup</pre>

                <div class="input-group">
                  {#if showApiKey}
                    <input
                      type="text"
                      placeholder="Enter your API key..."
                      bind:value={apiKeyInput}
                      on:keydown={(e) => e.key === 'Enter' && handleSaveApiKey()}
                      class="input-field"
                    />
                  {:else}
                    <input
                      type="password"
                      placeholder="Enter your API key..."
                      bind:value={apiKeyInput}
                      on:keydown={(e) => e.key === 'Enter' && handleSaveApiKey()}
                      class="input-field"
                    />
                  {/if}
                  <button
                    type="button"
                    class="btn-icon"
                    on:click={toggleShowApiKey}
                  >
                    {#if showApiKey}
                      <EyeOff class="w-4 h-4" />
                    {:else}
                      <Eye class="w-4 h-4" />
                    {/if}
                  </button>
                  <button
                    type="button"
                    class="btn-primary"
                    on:click={handleSaveApiKey}
                    disabled={!apiKeyInput.trim()}
                  >
                    Save API Key
                  </button>
                </div>
              {:else}
                <div class="key-display">
                  <span class="label">Current API Key:</span>
                  <code class="key-value">
                    {$apiConfig.apiKey.substring(0, 8)}...{$apiConfig.apiKey.substring($apiConfig.apiKey.length - 4)}
                  </code>
                </div>

                <div class="button-group">
                  <button
                    class="btn-secondary"
                    on:click={handleTestConnection}
                    disabled={testing}
                  >
                    {#if testing}
                      <RefreshCw class="w-4 h-4 animate-spin" />
                      Testing...
                    {:else}
                      Test Connection
                    {/if}
                  </button>

                  <button
                    class="btn-danger"
                    on:click={handleClearApiKey}
                  >
                    <Trash2 class="w-4 h-4" />
                    Remove API Key
                  </button>
                </div>

                {#if testResult === 'success'}
                  <div class="alert alert-success">
                    <Check class="w-4 h-4" />
                    API connection successful!
                  </div>
                {:else if testResult === 'error'}
                  <div class="alert alert-error">
                    <X class="w-4 h-4" />
                    {$apiConfig.authError || 'Connection failed'}
                  </div>
                {/if}
              {/if}
            </div>
          </div>
        {/if}

        {#if !isMobile || activeSection === 'display'}
          <!-- Display Preferences Section -->
          <div class="settings-section">
            <div class="section-header">
              <div class="section-title">
                <Monitor class="w-5 h-5" />
                <h2>Display Preferences</h2>
              </div>
            </div>

            <div class="section-content">
              <div class="preference-item">
                <div class="preference-info">
                  <label>Theme</label>
                  <span class="preference-description">Choose your preferred color scheme</span>
                </div>
                <div class="button-toggle">
                  <button
                    class="toggle-option {preferences.theme === 'light' ? 'active' : ''}"
                    on:click={() => handlePreferenceChange('theme', 'light')}
                  >
                    <Sun class="w-4 h-4" />
                    Light
                  </button>
                  <button
                    class="toggle-option {preferences.theme === 'dark' ? 'active' : ''}"
                    on:click={() => handlePreferenceChange('theme', 'dark')}
                  >
                    <Moon class="w-4 h-4" />
                    Dark
                  </button>
                </div>
              </div>

              <div class="preference-item">
                <div class="preference-info">
                  <label>Compact Mode</label>
                  <span class="preference-description">Reduce spacing for more content</span>
                </div>
                <label class="switch">
                  <input
                    type="checkbox"
                    bind:checked={preferences.compactMode}
                    on:change={() => handlePreferenceChange('compactMode', preferences.compactMode)}
                  />
                  <span class="slider"></span>
                </label>
              </div>

              <div class="preference-item">
                <div class="preference-info">
                  <label>Auto Refresh</label>
                  <span class="preference-description">Automatically update job status</span>
                </div>
                <label class="switch">
                  <input
                    type="checkbox"
                    bind:checked={preferences.autoRefresh}
                    on:change={() => handlePreferenceChange('autoRefresh', preferences.autoRefresh)}
                  />
                  <span class="slider"></span>
                </label>
              </div>

              <div class="preference-item">
                <div class="preference-info">
                  <label>Refresh Interval</label>
                  <span class="preference-description">How often to check for updates</span>
                </div>
                <select
                  class="select-field"
                  bind:value={preferences.refreshInterval}
                  on:change={() => handlePreferenceChange('refreshInterval', preferences.refreshInterval)}
                  disabled={!preferences.autoRefresh}
                >
                  <option value={10}>10 seconds</option>
                  <option value={30}>30 seconds</option>
                  <option value={60}>1 minute</option>
                  <option value={120}>2 minutes</option>
                  <option value={300}>5 minutes</option>
                </select>
              </div>

              <div class="preference-item">
                <div class="preference-info">
                  <label>Jobs Per Page</label>
                  <span class="preference-description">Number of jobs to display</span>
                </div>
                <select
                  class="select-field"
                  bind:value={preferences.jobsPerPage}
                  on:change={() => handlePreferenceChange('jobsPerPage', preferences.jobsPerPage)}
                >
                  <option value={25}>25</option>
                  <option value={50}>50</option>
                  <option value={100}>100</option>
                  <option value={200}>200</option>
                  <option value={500}>500</option>
                </select>
              </div>

              <div class="preference-item disabled">
                <div class="preference-info">
                  <label>Default Job View</label>
                  <span class="preference-description">How to display job listings (Coming soon)</span>
                </div>
                <div class="button-toggle disabled">
                  <button class="toggle-option disabled">Table</button>
                  <button class="toggle-option disabled">Cards</button>
                </div>
              </div>
            </div>
          </div>
        {/if}

        {#if !isMobile || activeSection === 'sync'}
          <!-- Sync Settings Section -->
          <div class="settings-section full-width">
            <div class="section-header collapsible" class:collapsed={collapsedSections.sync}>
              <div class="section-title">
                <RefreshCw class="w-5 h-5" />
                <h2>Sync Settings</h2>
              </div>
              <button
                class="collapse-btn"
                on:click={() => collapsedSections.sync = !collapsedSections.sync}
                title="{collapsedSections.sync ? 'Expand' : 'Collapse'} sync settings"
              >
                <ChevronRight class="w-4 h-4 collapse-icon {collapsedSections.sync ? '' : 'collapsed'}" />
              </button>
            </div>

            {#if !collapsedSections.sync}
              <div class="section-content">
                <SyncSettings />
              </div>
            {/if}
          </div>
        {/if}

        {#if !isMobile || activeSection === 'notifications'}
          <!-- Notifications Section -->
          <div class="settings-section">
            <div class="section-header">
              <div class="section-title">
                <Bell class="w-5 h-5" />
                <h2>Notifications</h2>
              </div>
            </div>

            <div class="section-content">
              <div class="preference-item">
                <div class="preference-info">
                  <label>Show Notifications</label>
                  <span class="preference-description">Browser notifications for job status changes</span>
                </div>
                <label class="switch">
                  <input
                    type="checkbox"
                    bind:checked={preferences.showNotifications}
                    on:change={() => handlePreferenceChange('showNotifications', preferences.showNotifications)}
                  />
                  <span class="slider"></span>
                </label>
              </div>

              <div class="preference-item">
                <div class="preference-info">
                  <label>Sound Alerts</label>
                  <span class="preference-description">Play sound when jobs complete</span>
                </div>
                <label class="switch">
                  <input
                    type="checkbox"
                    bind:checked={preferences.soundAlerts}
                    on:change={() => handlePreferenceChange('soundAlerts', preferences.soundAlerts)}
                    disabled={!preferences.showNotifications}
                  />
                  <span class="slider"></span>
                </label>
              </div>
            </div>
          </div>
        {/if}

        {#if !isMobile || activeSection === 'cache'}
          <!-- Cache Management Section -->
          <div class="settings-section">
            <div class="section-header">
              <div class="section-title">
                <Database class="w-5 h-5" />
                <h2>Cache Management</h2>
              </div>
            </div>

            <div class="section-content">
              <div class="cache-stats">
                <div class="stat">
                  <span class="stat-label">Cache Size</span>
                  <span class="stat-value">{cacheStats.size}</span>
                </div>
                <div class="stat">
                  <span class="stat-label">Cached Items</span>
                  <span class="stat-value">{cacheStats.entries}</span>
                </div>
                {#if cacheStats.lastCleared}
                  <div class="stat">
                    <span class="stat-label">Last Cleared</span>
                    <span class="stat-value">
                      {cacheStats.lastCleared.toLocaleDateString()}
                    </span>
                  </div>
                {/if}
              </div>

              <button
                class="btn-danger full-width"
                on:click={clearCache}
                disabled={clearingCache || !$apiConfig.apiKey}
              >
                {#if clearingCache}
                  <RefreshCw class="w-4 h-4 animate-spin" />
                  Clearing...
                {:else}
                  <Trash2 class="w-4 h-4" />
                  Clear All Cache
                {/if}
              </button>

              <div class="help-text">
                Clearing cache will remove all stored job data and require re-fetching from servers.
              </div>
            </div>
          </div>
        {/if}

        {#if !isMobile || activeSection === 'data'}
          <!-- Data & Privacy Section -->
          <div class="settings-section">
            <div class="section-header">
              <div class="section-title">
                <Shield class="w-5 h-5" />
                <h2>Data & Privacy</h2>
              </div>
            </div>

            <div class="section-content">
              <button
                class="btn-secondary full-width"
                on:click={exportSettings}
              >
                <Download class="w-4 h-4" />
                Export Settings
              </button>

              <button
                class="btn-secondary full-width"
                on:click={importSettings}
              >
                <Upload class="w-4 h-4" />
                Import Settings
              </button>

              <div class="help-text">
                Export your settings to back them up or transfer to another device. API keys are not included in exports for security.
              </div>
            </div>
          </div>
        {/if}
      </div>
    {/if}
  </div>
</div>

<style>
  .settings-container {
    padding: 1.5rem 2rem;
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
    max-width: 100%;
  }

  @media (min-width: 1024px) {
    .settings-container {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(450px, 1fr));
      grid-auto-rows: min-content;
      align-items: start;
    }
  }

  .settings-container.mobile-section {
    padding: 0;
    display: block;
  }

  .mobile-settings-list {
    background: white;
  }

  .settings-item {
    display: flex;
    align-items: center;
    width: 100%;
    padding: 1rem;
    background: white;
    border: none;
    border-bottom: 1px solid #e5e7eb;
    cursor: pointer;
    transition: background 0.15s;
    text-align: left;
  }

  .settings-item:hover {
    background: #f9fafb;
  }

  .item-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 40px;
    height: 40px;
    background: #f3f4f6;
    border-radius: 10px;
    margin-right: 1rem;
  }

  .item-content {
    flex: 1;
  }

  .item-title {
    font-weight: 500;
    color: #111827;
    margin-bottom: 0.25rem;
  }

  .item-subtitle {
    font-size: 0.875rem;
    color: #6b7280;
  }

  .settings-section {
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    padding: 1.5rem;
  }

  @media (min-width: 1024px) {
    .settings-section.full-width {
      grid-column: 1 / -1;
    }
  }

  .mobile-section .settings-section {
    border: none;
    border-radius: 0;
    margin: 0;
  }

  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1.5rem;
    padding-bottom: 1rem;
    border-bottom: 1px solid #f3f4f6;
  }

  .section-header.collapsible {
    cursor: pointer;
    transition: all 0.2s ease;
    margin-bottom: 0;
  }

  .section-header.collapsible:hover {
    background: #fafbfc;
    border-radius: 8px;
    padding: 0.75rem 1rem;
    margin: -0.75rem -1rem 0 -1rem;
  }

  .section-header.collapsed {
    border-bottom: none;
    margin-bottom: 0;
  }

  .section-title {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .section-title h2 {
    font-size: 1.125rem;
    font-weight: 600;
    color: #111827;
    margin: 0;
  }

  .section-content {
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
  }

  .collapse-btn {
    background: none;
    border: none;
    cursor: pointer;
    padding: 0.375rem;
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s ease;
    color: #6b7280;
  }

  .collapse-btn:hover {
    background: #f3f4f6;
    color: #374151;
  }

  .collapse-icon {
    transition: transform 0.2s ease;
  }

  .collapse-icon.collapsed {
    transform: rotate(90deg);
  }

  .preference-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.75rem 0;
  }

  .preference-info {
    flex: 1;
  }

  .preference-info label {
    display: block;
    font-weight: 500;
    color: #111827;
    margin-bottom: 0.25rem;
  }

  .preference-description {
    font-size: 0.875rem;
    color: #6b7280;
  }

  .status-badge {
    display: inline-flex;
    align-items: center;
    padding: 0.25rem 0.75rem;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 500;
    background: #f3f4f6;
    color: #6b7280;
  }

  .status-badge.success {
    background: #d1fae5;
    color: #065f46;
  }

  .status-badge.warning {
    background: #fed7aa;
    color: #92400e;
  }

  .help-text {
    font-size: 0.875rem;
    color: #6b7280;
    line-height: 1.5;
  }

  .command {
    background: #1f2937;
    color: #f3f4f6;
    padding: 0.75rem 1rem;
    border-radius: 8px;
    font-family: 'SF Mono', 'Monaco', 'Courier New', monospace;
    font-size: 0.875rem;
    margin: 0.75rem 0;
  }

  .input-group {
    display: flex;
    gap: 0.5rem;
  }

  .input-field {
    flex: 1;
    padding: 0.625rem 1rem;
    border: 1px solid #d1d5db;
    border-radius: 8px;
    font-size: 0.875rem;
    transition: all 0.15s;
  }

  .input-field:focus {
    outline: none;
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  .button-group {
    display: flex;
    gap: 0.75rem;
  }

  .btn-primary,
  .btn-secondary,
  .btn-danger,
  .btn-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    padding: 0.625rem 1rem;
    border-radius: 8px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
    border: none;
  }

  .btn-primary {
    background: #3b82f6;
    color: white;
  }

  .btn-primary:hover:not(:disabled) {
    background: #2563eb;
  }

  .btn-primary:disabled,
  .btn-danger:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn-secondary {
    background: white;
    color: #374151;
    border: 1px solid #d1d5db;
  }

  .btn-secondary:hover {
    background: #f9fafb;
  }

  .btn-danger {
    background: white;
    color: #dc2626;
    border: 1px solid #fecaca;
  }

  .btn-danger:hover {
    background: #fef2f2;
  }

  .btn-icon {
    padding: 0.625rem;
    background: white;
    border: 1px solid #d1d5db;
  }

  .btn-icon:hover {
    background: #f9fafb;
  }

  .full-width {
    width: 100%;
  }

  .key-display {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 1rem;
    background: #f9fafb;
    border-radius: 8px;
  }

  .key-display .label {
    font-weight: 500;
    color: #374151;
  }

  .key-value {
    font-family: 'SF Mono', 'Monaco', 'Courier New', monospace;
    font-size: 0.875rem;
    color: #3b82f6;
  }

  .alert {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.75rem 1rem;
    border-radius: 8px;
    font-size: 0.875rem;
  }

  .alert-success {
    background: #d1fae5;
    color: #065f46;
    border: 1px solid #6ee7b7;
  }

  .alert-error {
    background: #fee2e2;
    color: #991b1b;
    border: 1px solid #fca5a5;
  }

  /* Toggle Switch */
  .switch {
    position: relative;
    display: inline-block;
    width: 48px;
    height: 24px;
  }

  .switch input {
    opacity: 0;
    width: 0;
    height: 0;
  }

  .slider {
    position: absolute;
    cursor: pointer;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: #cbd5e1;
    transition: 0.3s;
    border-radius: 24px;
  }

  .slider:before {
    position: absolute;
    content: "";
    height: 18px;
    width: 18px;
    left: 3px;
    bottom: 3px;
    background-color: white;
    transition: 0.3s;
    border-radius: 50%;
  }

  input:checked + .slider {
    background-color: #3b82f6;
  }

  input:checked + .slider:before {
    transform: translateX(24px);
  }

  /* Button Toggle */
  .button-toggle {
    display: flex;
    background: #f3f4f6;
    border-radius: 8px;
    padding: 2px;
  }

  .toggle-option {
    flex: 1;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.375rem;
    padding: 0.5rem 1rem;
    background: transparent;
    border: none;
    border-radius: 6px;
    font-size: 0.875rem;
    font-weight: 500;
    color: #6b7280;
    cursor: pointer;
    transition: all 0.15s;
  }

  .toggle-option.active {
    background: white;
    color: #111827;
    box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
  }

  .select-field {
    padding: 0.625rem 1rem;
    border: 1px solid #d1d5db;
    border-radius: 8px;
    font-size: 0.875rem;
    background: white;
    cursor: pointer;
    transition: all 0.15s;
  }

  .select-field:focus {
    outline: none;
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  .select-field:disabled {
    opacity: 0.6;
    cursor: not-allowed;
    background: #f9fafb;
  }

  /* Cache Stats */
  .cache-stats {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    gap: 1rem;
    padding: 1rem;
    background: #f9fafb;
    border-radius: 8px;
  }

  .stat {
    display: flex;
    flex-direction: column;
  }

  .stat-label {
    font-size: 0.75rem;
    color: #6b7280;
    margin-bottom: 0.25rem;
  }

  .stat-value {
    font-size: 1.125rem;
    font-weight: 600;
    color: #111827;
  }

  /* Animations */
  .animate-spin {
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }

  /* Disabled state styles */
  .preference-item.disabled {
    opacity: 0.6;
    pointer-events: none;
  }

  .preference-item.disabled label {
    color: #9ca3af;
  }

  .preference-item.disabled .preference-description {
    color: #d1d5db;
  }

  .switch.disabled {
    opacity: 0.6;
  }

  .switch.disabled input {
    cursor: not-allowed;
  }

  .button-toggle.disabled {
    opacity: 0.6;
    pointer-events: none;
  }

  .toggle-option.disabled {
    opacity: 0.6;
    cursor: not-allowed;
    pointer-events: none;
  }

  /* Compact Mode - Global styles */
  :global(.compact-mode) {
    --spacing-xs: 0.125rem;
    --spacing-sm: 0.25rem;
    --spacing-md: 0.5rem;
    --spacing-lg: 0.75rem;
    --spacing-xl: 1rem;
  }

  :global(.compact-mode .settings-section) {
    padding: 1rem;
  }

  :global(.compact-mode .preference-item) {
    padding: 0.5rem 0;
  }

  :global(.compact-mode .section-header) {
    margin-bottom: 1rem;
    padding-bottom: 0.5rem;
  }

  :global(.compact-mode .section-content) {
    gap: 0.75rem;
  }

  /* Mobile responsive */
  @media (max-width: 768px) {
    .settings-container {
      padding: 1rem;
      gap: 1rem;
    }

    .preference-item {
      flex-direction: column;
      align-items: flex-start;
      gap: 0.75rem;
    }

    .button-toggle,
    .switch,
    .select-field {
      width: 100%;
    }

    .button-group {
      flex-direction: column;
    }

    .button-group button {
      width: 100%;
    }

    .settings-section {
      padding: 1rem;
    }
  }

  /* Large screens - better utilize space */
  @media (min-width: 1400px) {
    .settings-container {
      padding: 1.5rem 3rem;
      grid-template-columns: repeat(auto-fit, minmax(450px, 1fr));
    }
  }
</style>