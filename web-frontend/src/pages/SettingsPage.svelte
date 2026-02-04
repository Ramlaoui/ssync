<script lang="ts">
  import { onMount } from 'svelte';
  import { push } from 'svelte-spa-router';
  import Badge from '../lib/components/ui/Badge.svelte';
  import NavigationHeader from '../components/NavigationHeader.svelte';
  import SyncSettings from '../components/SyncSettings.svelte';
  import { apiConfig, setApiKey, clearApiKey, testConnection } from '../services/api';
  import { enableWebPush, disableWebPush, isWebPushSupported } from '../services/webpush';
  import { preferences as globalPreferences, preferencesActions } from '../stores/preferences';
  import { theme } from '../stores/theme';
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
    Settings as SettingsIcon,
    Wifi
  } from 'lucide-svelte';

  // Mobile detection
  let isMobile = $state(typeof window !== 'undefined' && window.innerWidth < 768);

  // API Key state
  let showApiKey = $state(false);
  let apiKeyInput = $state('');
  let testing = $state(false);
  let testResult: 'success' | 'error' | null = $state(null);

  interface LocalPreferences {
    autoRefresh: boolean;
    refreshInterval: number;
    compactMode: boolean;
    showNotifications: boolean;
    soundAlerts: boolean;
    webPushEnabled: boolean;
    jobsPerPage: number;
    defaultJobView: string;
    showCompletedJobs: boolean;
    groupJobsByHost: boolean;
  }

  // UI Preferences (stored in localStorage) - theme now managed by theme store
  let preferences = $state<LocalPreferences>({
    autoRefresh: false,
    refreshInterval: 30,
    compactMode: false,
    showNotifications: false,
    soundAlerts: false,
    webPushEnabled: false,
    jobsPerPage: 50,
    defaultJobView: 'table',
    showCompletedJobs: true,
    groupJobsByHost: false
  });

  // Auto-refresh timer
  let refreshTimer: number | null = null;

  // Cache stats
  let cacheStats = $state({
    size: '0 MB',
    entries: 0,
    lastCleared: null as Date | null
  });
  let loadingCacheStats = false;
  let clearingCache = $state(false);

  // Active section for mobile
  let activeSection: string | null = $state(null);

  // Collapsible sections state - expand on mobile when viewing sync section
  let collapsedSections = $derived({
    sync: !(isMobile && activeSection === 'sync') // Expand on mobile when viewing sync section
  });

  // WebSocket settings from global preferences
  let websocketConfig = $derived($globalPreferences.websocket);
  let webPushSupported = $state(false);

  let isConfigured = $derived($apiConfig.apiKey !== '');

  function checkMobile() {
    isMobile = window.innerWidth < 768;
  }

  onMount(() => {
    checkMobile();
    window.addEventListener('resize', checkMobile);

    // Load preferences from localStorage
    loadPreferences();

    isWebPushSupported().then((supported) => {
      webPushSupported = supported;
      if (!supported && preferences.webPushEnabled) {
        preferences.webPushEnabled = false;
        savePreferences();
      }
    });

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

  async function handlePreferenceChange(key: keyof LocalPreferences, value: any) {
    preferences = { ...preferences, [key]: value } as LocalPreferences;
    savePreferences();

    // Apply changes immediately
    if (key === 'compactMode') {
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
    } else if (key === 'webPushEnabled') {
      if (!webPushSupported) {
        preferences.webPushEnabled = false;
        savePreferences();
        return;
      }

      try {
        if (value) {
          await enableWebPush();
        } else {
          await disableWebPush();
        }
      } catch (e) {
        console.error('Failed to update Web Push:', e);
        preferences.webPushEnabled = false;
        savePreferences();
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

  // WebSocket settings update functions
  function updateWebSocketSetting(key: string, value: number | boolean) {
    preferencesActions.setWebSocketConfig({ [key]: value });
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
    const titles: Record<string, string> = {
      'api': 'API Authentication',
      'display': 'Display Preferences',
      'sync': 'Sync Settings',
      'notifications': 'Notifications',
      'cache': 'Cache Management',
      'websocket': 'WebSocket Connection',
      'data': 'Data & Privacy'
    };
    return titles[section] || 'Settings';
  }
</script>

<div class="h-full flex flex-col bg-background">
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
          class="flex items-center w-full p-4 bg-white dark:bg-card border-0 border-b border-gray-200 dark:border-border cursor-pointer transition-colors hover:bg-gray-50 dark:hover:bg-secondary text-left"
          onclick={() => activeSection = 'api'}
        >
          <div class="flex items-center justify-center w-10 h-10 bg-gray-100 dark:bg-secondary rounded-[10px] mr-4">
            <Key class="w-5 h-5 text-gray-600 dark:text-gray-400" />
          </div>
          <div class="flex-1">
            <div class="font-medium text-gray-900 dark:text-foreground mb-1">API Authentication</div>
            <div class="text-sm text-gray-500 dark:text-gray-400">
              {#if $apiConfig.authenticated}
                <Badge variant="success">Connected</Badge>
              {:else if isConfigured}
                <Badge variant="warning">Not authenticated</Badge>
              {:else}
                <Badge variant="secondary">Not configured</Badge>
              {/if}
            </div>
          </div>
          <ChevronRight class="w-4 h-4 text-gray-400 dark:text-gray-500" />
        </button>

        <button
          class="flex items-center w-full p-4 bg-white dark:bg-card border-0 border-b border-gray-200 dark:border-border cursor-pointer transition-colors hover:bg-gray-50 dark:hover:bg-secondary text-left"
          onclick={() => activeSection = 'display'}
        >
          <div class="flex items-center justify-center w-10 h-10 bg-gray-100 dark:bg-secondary rounded-[10px] mr-4">
            <Monitor class="w-5 h-5 text-gray-600 dark:text-gray-400" />
          </div>
          <div class="flex-1">
            <div class="font-medium text-gray-900 dark:text-foreground mb-1">Display Preferences</div>
            <div class="text-sm text-gray-500 dark:text-gray-400">Theme, layout, and appearance</div>
          </div>
          <ChevronRight class="w-4 h-4 text-gray-400 dark:text-gray-500" />
        </button>

        <button
          class="flex items-center w-full p-4 bg-white dark:bg-card border-0 border-b border-gray-200 dark:border-border cursor-pointer transition-colors hover:bg-gray-50 dark:hover:bg-secondary text-left"
          onclick={() => activeSection = 'sync'}
        >
          <div class="flex items-center justify-center w-10 h-10 bg-gray-100 dark:bg-secondary rounded-[10px] mr-4">
            <RefreshCw class="w-5 h-5 text-gray-600 dark:text-gray-400" />
          </div>
          <div class="flex-1">
            <div class="font-medium text-gray-900 dark:text-foreground mb-1">Sync Settings</div>
            <div class="text-sm text-gray-500 dark:text-gray-400">File patterns and filters</div>
          </div>
          <ChevronRight class="w-4 h-4 text-gray-400 dark:text-gray-500" />
        </button>

        <button
          class="flex items-center w-full p-4 bg-white dark:bg-card border-0 border-b border-gray-200 dark:border-border cursor-pointer transition-colors hover:bg-gray-50 dark:hover:bg-secondary text-left"
          onclick={() => activeSection = 'notifications'}
        >
          <div class="flex items-center justify-center w-10 h-10 bg-gray-100 dark:bg-secondary rounded-[10px] mr-4">
            <Bell class="w-5 h-5 text-gray-600 dark:text-gray-400" />
          </div>
          <div class="flex-1">
            <div class="font-medium text-gray-900 dark:text-foreground mb-1">Notifications</div>
            <div class="text-sm text-gray-500 dark:text-gray-400">Alerts and sounds</div>
          </div>
          <ChevronRight class="w-4 h-4 text-gray-400 dark:text-gray-500" />
        </button>

        <button
          class="flex items-center w-full p-4 bg-white dark:bg-card border-0 border-b border-gray-200 dark:border-border cursor-pointer transition-colors hover:bg-gray-50 dark:hover:bg-secondary text-left"
          onclick={() => activeSection = 'cache'}
        >
          <div class="flex items-center justify-center w-10 h-10 bg-gray-100 dark:bg-secondary rounded-[10px] mr-4">
            <Database class="w-5 h-5 text-gray-600 dark:text-gray-400" />
          </div>
          <div class="flex-1">
            <div class="font-medium text-gray-900 dark:text-foreground mb-1">Cache Management</div>
            <div class="text-sm text-gray-500 dark:text-gray-400">{cacheStats.size} used</div>
          </div>
          <ChevronRight class="w-4 h-4 text-gray-400 dark:text-gray-500" />
        </button>

        <button
          class="flex items-center w-full p-4 bg-white dark:bg-card border-0 border-b border-gray-200 dark:border-border cursor-pointer transition-colors hover:bg-gray-50 dark:hover:bg-secondary text-left"
          onclick={() => activeSection = 'websocket'}
        >
          <div class="flex items-center justify-center w-10 h-10 bg-gray-100 dark:bg-secondary rounded-[10px] mr-4">
            <Wifi class="w-5 h-5 text-gray-600 dark:text-gray-400" />
          </div>
          <div class="flex-1">
            <div class="font-medium text-gray-900 dark:text-foreground mb-1">WebSocket Connection</div>
            <div class="text-sm text-gray-500 dark:text-gray-400">Real-time updates settings</div>
          </div>
          <ChevronRight class="w-4 h-4 text-gray-400 dark:text-gray-500" />
        </button>

        <button
          class="flex items-center w-full p-4 bg-white dark:bg-card border-0 border-b border-gray-200 dark:border-border cursor-pointer transition-colors hover:bg-gray-50 dark:hover:bg-secondary text-left"
          onclick={() => activeSection = 'data'}
        >
          <div class="flex items-center justify-center w-10 h-10 bg-gray-100 dark:bg-secondary rounded-[10px] mr-4">
            <Shield class="w-5 h-5 text-gray-600 dark:text-gray-400" />
          </div>
          <div class="flex-1">
            <div class="font-medium text-gray-900 dark:text-foreground mb-1">Data & Privacy</div>
            <div class="text-sm text-gray-500 dark:text-gray-400">Export and import settings</div>
          </div>
          <ChevronRight class="w-4 h-4 text-gray-400 dark:text-gray-500" />
        </button>
      </div>
    {:else}
      <!-- Desktop: Grid layout / Mobile: Section view -->
      <div class="p-4 grid gap-4 lg:grid-cols-2 xl:grid-cols-3 {isMobile ? 'grid-cols-1' : ''}">
        {#if !isMobile || activeSection === 'api'}
          <!-- API Authentication Section -->
          <div class="settings-section {activeSection === 'sync' ? 'lg:col-span-2 xl:col-span-3' : ''}">
            <div class="section-header">
              <div class="section-title">
                <Key class="w-5 h-5" />
                <h2>API Authentication</h2>
              </div>
              {#if $apiConfig.authenticated}
                <Badge variant="success">Connected</Badge>
              {:else if isConfigured}
                <Badge variant="warning">Not authenticated</Badge>
              {:else}
                <Badge variant="secondary">Not configured</Badge>
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
                      onkeydown={(e) => e.key === 'Enter' && handleSaveApiKey()}
                      class="input-field"
                    />
                  {:else}
                    <input
                      type="password"
                      placeholder="Enter your API key..."
                      bind:value={apiKeyInput}
                      onkeydown={(e) => e.key === 'Enter' && handleSaveApiKey()}
                      class="input-field"
                    />
                  {/if}
                  <button
                    type="button"
                    class="btn-icon"
                    onclick={toggleShowApiKey}
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
                    onclick={handleSaveApiKey}
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
                    onclick={handleTestConnection}
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
                    onclick={handleClearApiKey}
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
                  <span class="preference-label">Theme</span>
                  <span class="preference-description">Choose your preferred color scheme</span>
                </div>
                <div class="button-toggle">
                  <button
                    class="toggle-option {$theme === 'light' ? 'active' : ''}"
                    onclick={() => theme.set('light')}
                  >
                    <Sun class="w-4 h-4" />
                    Light
                  </button>
                  <button
                    class="toggle-option {$theme === 'dark' ? 'active' : ''}"
                    onclick={() => theme.set('dark')}
                  >
                    <Moon class="w-4 h-4" />
                    Dark
                  </button>
                  <button
                    class="toggle-option {$theme === 'system' ? 'active' : ''}"
                    onclick={() => theme.set('system')}
                  >
                    <Monitor class="w-4 h-4" />
                    System
                  </button>
                </div>
              </div>

              <div class="preference-item">
                <div class="preference-info">
                  <span class="preference-label">Compact Mode</span>
                  <span class="preference-description">Reduce spacing for more content</span>
                </div>
                <label class="switch">
                  <input
                    type="checkbox"
                    bind:checked={preferences.compactMode}
                    onchange={() => handlePreferenceChange('compactMode', preferences.compactMode)}
                  />
                  <span class="slider"></span>
                </label>
              </div>

              <div class="preference-item">
                <div class="preference-info">
                  <span class="preference-label">Auto Refresh</span>
                  <span class="preference-description">Automatically update job status</span>
                </div>
                <label class="switch">
                  <input
                    type="checkbox"
                    bind:checked={preferences.autoRefresh}
                    onchange={() => handlePreferenceChange('autoRefresh', preferences.autoRefresh)}
                  />
                  <span class="slider"></span>
                </label>
              </div>

              <div class="preference-item">
                <div class="preference-info">
                  <span class="preference-label">Refresh Interval</span>
                  <span class="preference-description">How often to check for updates</span>
                </div>
                <select
                  class="select-field"
                  bind:value={preferences.refreshInterval}
                  onchange={() => handlePreferenceChange('refreshInterval', preferences.refreshInterval)}
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
                  <span class="preference-label">Jobs Per Page</span>
                  <span class="preference-description">Number of jobs to display</span>
                </div>
                <select
                  class="select-field"
                  bind:value={preferences.jobsPerPage}
                  onchange={() => handlePreferenceChange('jobsPerPage', preferences.jobsPerPage)}
                >
                  <option value={25}>25</option>
                  <option value={50}>50</option>
                  <option value={100}>100</option>
                  <option value={200}>200</option>
                  <option value={500}>500</option>
                </select>
              </div>

              <div class="preference-item">
                <div class="preference-info">
                  <span class="preference-label">Default History Window</span>
                  <span class="preference-description">How far back to load completed jobs</span>
                </div>
                <select
                  class="select-field"
                  value={$globalPreferences.defaultSince}
                  onchange={(event) => preferencesActions.setDefaultSince(event.currentTarget.value)}
                >
                  <option value="1d">Last 1 day</option>
                  <option value="3d">Last 3 days</option>
                  <option value="7d">Last 7 days</option>
                  <option value="14d">Last 14 days</option>
                  <option value="30d">Last 30 days</option>
                </select>
              </div>

              <div class="preference-item disabled">
                <div class="preference-info">
                  <span class="preference-label">Default Job View</span>
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
                onclick={() => collapsedSections.sync = !collapsedSections.sync}
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
                  <span class="preference-label">Show Notifications</span>
                  <span class="preference-description">Browser notifications for job status changes</span>
                </div>
                <label class="switch">
                  <input
                    type="checkbox"
                    bind:checked={preferences.showNotifications}
                    onchange={() => handlePreferenceChange('showNotifications', preferences.showNotifications)}
                  />
                  <span class="slider"></span>
                </label>
              </div>

              <div class="preference-item">
                <div class="preference-info">
                  <span class="preference-label">Web Push</span>
                  <span class="preference-description">Receive notifications even when the browser is closed</span>
                </div>
                <label class="switch">
                  <input
                    type="checkbox"
                    bind:checked={preferences.webPushEnabled}
                    onchange={() => handlePreferenceChange('webPushEnabled', preferences.webPushEnabled)}
                    disabled={!webPushSupported}
                  />
                  <span class="slider"></span>
                </label>
              </div>

              <div class="preference-item">
                <div class="preference-info">
                  <span class="preference-label">Sound Alerts</span>
                  <span class="preference-description">Play sound when jobs complete</span>
                </div>
                <label class="switch">
                  <input
                    type="checkbox"
                    bind:checked={preferences.soundAlerts}
                    onchange={() => handlePreferenceChange('soundAlerts', preferences.soundAlerts)}
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
                onclick={clearCache}
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

        {#if !isMobile || activeSection === 'websocket'}
          <!-- WebSocket Connection Settings -->
          <div class="settings-section">
            <div class="section-header">
              <div class="section-title">
                <Wifi class="w-5 h-5" />
                <h2>WebSocket Connection</h2>
              </div>
            </div>

            <div class="section-content">
              <div class="form-group">
                <label class="toggle-label">
                  <input
                    type="checkbox"
                    checked={websocketConfig.autoReconnect}
                    onchange={(e) => updateWebSocketSetting('autoReconnect', (e.target as HTMLInputElement).checked)}
                  />
                  <span>Auto-reconnect</span>
                </label>
                <div class="help-text">
                  Automatically reconnect to the server when connection is lost
                </div>
              </div>

              <div class="form-group">
                <label>
                  <span class="block font-medium text-gray-700 mb-2">Initial Retry Delay</span>
                  <div class="flex items-center gap-2">
                    <input
                      type="number"
                      min="100"
                      max="10000"
                      step="100"
                      value={websocketConfig.initialRetryDelay}
                      oninput={(e) => updateWebSocketSetting('initialRetryDelay', parseInt((e.target as HTMLInputElement).value) || 1000)}
                      class="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    />
                    <span class="text-sm text-gray-500 font-medium min-w-[30px]">ms</span>
                  </div>
                </label>
                <div class="help-text">
                  Initial delay before first reconnection attempt (default: 1000ms)
                </div>
              </div>

              <div class="form-group">
                <label>
                  <span class="block font-medium text-gray-700 mb-2">Maximum Retry Delay</span>
                  <div class="flex items-center gap-2">
                    <input
                      type="number"
                      min="1000"
                      max="120000"
                      step="1000"
                      value={websocketConfig.maxRetryDelay}
                      oninput={(e) => updateWebSocketSetting('maxRetryDelay', parseInt((e.target as HTMLInputElement).value) || 30000)}
                      class="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    />
                    <span class="text-sm text-gray-500 font-medium min-w-[30px]">ms</span>
                  </div>
                </label>
                <div class="help-text">
                  Maximum delay between reconnection attempts (default: 30000ms)
                </div>
              </div>

              <div class="form-group">
                <label>
                  <span class="block font-medium text-gray-700 mb-2">Backoff Multiplier</span>
                  <input
                    type="number"
                    min="1"
                    max="3"
                    step="0.1"
                    value={websocketConfig.retryBackoffMultiplier}
                    oninput={(e) => updateWebSocketSetting('retryBackoffMultiplier', parseFloat((e.target as HTMLInputElement).value) || 1.5)}
                    class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  />
                </label>
                <div class="help-text">
                  Exponential backoff factor for retry delays (default: 1.5)
                </div>
              </div>

              <div class="form-group">
                <label>
                  <span class="block font-medium text-gray-700 mb-2">Connection Timeout</span>
                  <div class="flex items-center gap-2">
                    <input
                      type="number"
                      min="5000"
                      max="120000"
                      step="5000"
                      value={websocketConfig.timeout}
                      oninput={(e) => updateWebSocketSetting('timeout', parseInt((e.target as HTMLInputElement).value) || 45000)}
                      class="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    />
                    <span class="text-sm text-gray-500 font-medium min-w-[30px]">ms</span>
                  </div>
                </label>
                <div class="help-text">
                  Time without activity before connection is considered unhealthy (default: 45000ms)
                </div>
              </div>

              <div class="flex gap-3 p-4 bg-blue-50 border border-blue-200 rounded-lg text-sm text-blue-900">
                <Monitor class="w-4 h-4 flex-shrink-0 mt-0.5" />
                <div>
                  <strong class="text-blue-950">About WebSocket Connection:</strong><br/>
                  Real-time updates use WebSocket for instant job status changes. If auto-reconnect is enabled,
                  the system will automatically try to restore connection with exponential backoff.
                </div>
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
                onclick={exportSettings}
              >
                <Download class="w-4 h-4" />
                Export Settings
              </button>

              <button
                class="btn-secondary full-width"
                onclick={importSettings}
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
  .settings-section {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.5rem;
  }

  @media (min-width: 1024px) {
    .settings-section.full-width {
      grid-column: 1 / -1;
    }
  }

  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1.5rem;
    padding-bottom: 1rem;
    border-bottom: 1px solid var(--border);
  }

  .section-header.collapsible {
    cursor: pointer;
    transition: all 0.2s ease;
    margin-bottom: 0;
  }

  .section-header.collapsible:hover {
    background: var(--secondary);
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
    color: var(--foreground);
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
    color: var(--muted-foreground);
  }

  .collapse-btn:hover {
    background: var(--secondary);
    color: var(--foreground);
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

  .preference-label {
    display: block;
    font-weight: 500;
    color: var(--foreground);
    margin-bottom: 0.25rem;
  }

  .preference-description {
    font-size: 0.875rem;
    color: var(--muted-foreground);
  }

  .help-text {
    font-size: 0.875rem;
    color: var(--muted-foreground);
    line-height: 1.5;
  }

  .command {
    background: var(--secondary);
    color: var(--secondary-foreground);
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
    border: 1px solid var(--border);
    border-radius: 8px;
    font-size: 0.875rem;
    background: var(--input);
    color: var(--foreground);
    transition: all 0.15s;
  }

  .input-field:focus {
    outline: none;
    border-color: var(--ring);
    box-shadow: 0 0 0 3px var(--ring);
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
    background: var(--primary);
    color: var(--primary-foreground);
  }

  .btn-primary:hover:not(:disabled) {
    opacity: 0.9;
  }

  .btn-primary:disabled,
  .btn-danger:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn-secondary {
    background: var(--secondary);
    color: var(--secondary-foreground);
    border: 1px solid var(--border);
  }

  .btn-secondary:hover {
    opacity: 0.9;
  }

  .btn-danger {
    background: var(--destructive);
    color: var(--destructive-foreground);
    border: 1px solid var(--destructive);
  }

  .btn-danger:hover {
    opacity: 0.9;
  }

  .btn-icon {
    padding: 0.625rem;
    background: var(--secondary);
    border: 1px solid var(--border);
    color: var(--foreground);
  }

  .btn-icon:hover {
    opacity: 0.9;
  }

  .full-width {
    width: 100%;
  }

  .key-display {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 1rem;
    background: var(--secondary);
    border-radius: 8px;
  }

  .key-display .label {
    font-weight: 500;
    color: var(--foreground);
  }

  .key-value {
    font-family: 'SF Mono', 'Monaco', 'Courier New', monospace;
    font-size: 0.875rem;
    color: var(--accent);
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
    background: var(--success-bg);
    color: var(--success);
    border: 1px solid var(--success);
  }

  .alert-error {
    background: var(--error-bg);
    color: var(--error);
    border: 1px solid var(--error);
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
    background-color: var(--muted);
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
    background-color: var(--background);
    transition: 0.3s;
    border-radius: 50%;
  }

  input:checked + .slider {
    background-color: var(--accent);
  }

  input:checked + .slider:before {
    transform: translateX(24px);
  }

  /* Button Toggle */
  .button-toggle {
    display: flex;
    background: var(--secondary);
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
    color: var(--muted-foreground);
    cursor: pointer;
    transition: all 0.15s;
  }

  .toggle-option.active {
    background: var(--background);
    color: var(--foreground);
    box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
  }

  .select-field {
    padding: 0.625rem 1rem;
    border: 1px solid var(--border);
    border-radius: 8px;
    font-size: 0.875rem;
    background: var(--input);
    color: var(--foreground);
    cursor: pointer;
    transition: all 0.15s;
  }

  .select-field:focus {
    outline: none;
    border-color: var(--ring);
    box-shadow: 0 0 0 3px var(--ring);
  }

  .select-field:disabled {
    opacity: 0.6;
    cursor: not-allowed;
    background: var(--secondary);
  }

  /* Cache Stats */
  .cache-stats {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    gap: 1rem;
    padding: 1rem;
    background: var(--secondary);
    border-radius: 8px;
  }

  .stat {
    display: flex;
    flex-direction: column;
  }

  .stat-label {
    font-size: 0.75rem;
    color: var(--muted-foreground);
    margin-bottom: 0.25rem;
  }

  .stat-value {
    font-size: 1.125rem;
    font-weight: 600;
    color: var(--foreground);
  }

  /* Disabled state styles */
  .preference-item.disabled {
    opacity: 0.6;
    pointer-events: none;
  }

  .preference-item.disabled .preference-label {
    color: var(--muted-foreground);
  }

  .preference-item.disabled .preference-description {
    color: var(--muted-foreground);
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
</style>
