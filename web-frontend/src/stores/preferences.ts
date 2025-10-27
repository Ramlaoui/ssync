import { writable } from 'svelte/store';

interface WebSocketConfig {
  initialRetryDelay: number;    // milliseconds
  maxRetryDelay: number;         // milliseconds
  retryBackoffMultiplier: number;
  timeout: number;               // milliseconds
  autoReconnect: boolean;
}

interface UIPreferences {
  groupArrayJobs: boolean;
  autoRefresh: boolean;
  refreshInterval: number;
  showMetrics: boolean;
  websocket: WebSocketConfig;
}

const defaultPreferences: UIPreferences = {
  groupArrayJobs: false,  // Default to ungrouped, user can enable after data loads
  autoRefresh: true,
  refreshInterval: 30000,  // 30 seconds
  showMetrics: false,
  websocket: {
    initialRetryDelay: 1000,     // 1 second
    maxRetryDelay: 30000,        // 30 seconds
    retryBackoffMultiplier: 1.5,
    timeout: 45000,              // 45 seconds
    autoReconnect: true,
  },
};

// Load preferences from localStorage
function loadPreferences(): UIPreferences {
  if (typeof window === 'undefined') {
    return defaultPreferences;
  }

  const stored = localStorage.getItem('ui-preferences');
  if (stored) {
    try {
      return { ...defaultPreferences, ...JSON.parse(stored) };
    } catch {
      return defaultPreferences;
    }
  }
  return defaultPreferences;
}

// Create the store
const initialPreferences = loadPreferences();
export const preferences = writable<UIPreferences>(initialPreferences);

// Save to localStorage whenever preferences change
preferences.subscribe((value) => {
  if (typeof window !== 'undefined') {
    localStorage.setItem('ui-preferences', JSON.stringify(value));
  }
});

// Export helper functions
export const preferencesActions = {
  toggleArrayGrouping: () => {
    preferences.update(p => ({ ...p, groupArrayJobs: !p.groupArrayJobs }));
  },

  setArrayGrouping: (enabled: boolean) => {
    preferences.update(p => ({ ...p, groupArrayJobs: enabled }));
  },

  toggleAutoRefresh: () => {
    preferences.update(p => ({ ...p, autoRefresh: !p.autoRefresh }));
  },

  setAutoRefresh: (enabled: boolean) => {
    preferences.update(p => ({ ...p, autoRefresh: enabled }));
  },

  setRefreshInterval: (interval: number) => {
    preferences.update(p => ({ ...p, refreshInterval: interval }));
  },

  toggleMetrics: () => {
    preferences.update(p => ({ ...p, showMetrics: !p.showMetrics }));
  },

  setWebSocketConfig: (config: Partial<WebSocketConfig>) => {
    preferences.update(p => ({
      ...p,
      websocket: { ...p.websocket, ...config }
    }));
  },

  toggleAutoReconnect: () => {
    preferences.update(p => ({
      ...p,
      websocket: { ...p.websocket, autoReconnect: !p.websocket.autoReconnect }
    }));
  },

  reset: () => {
    preferences.set(defaultPreferences);
  }
};

// Export types for use in other modules
export type { UIPreferences, WebSocketConfig };