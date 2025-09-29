import { writable } from 'svelte/store';

interface UIPreferences {
  groupArrayJobs: boolean;
  autoRefresh: boolean;
  refreshInterval: number;
  showMetrics: boolean;
}

const defaultPreferences: UIPreferences = {
  groupArrayJobs: true,  // Default to grouping array jobs
  autoRefresh: true,
  refreshInterval: 30000,  // 30 seconds
  showMetrics: false,
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

  reset: () => {
    preferences.set(defaultPreferences);
  }
};