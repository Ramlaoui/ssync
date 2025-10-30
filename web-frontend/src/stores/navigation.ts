import { writable } from 'svelte/store';
import { push } from 'svelte-spa-router';

// Storage key for persistence
const NAVIGATION_STORAGE_KEY = 'ssync_navigation_state';

interface NavigationState {
  previousRoute?: string;
  context?: 'job' | 'watcher' | 'home' | 'launch';
  jobId?: string;
  hostname?: string;
  breadcrumbs?: Array<{
    label: string;
    route: string;
  }>;
  skipNextUpdate?: boolean; // Flag to skip the next automatic update
}

// Load initial state from localStorage if available
function loadFromStorage(): NavigationState {
  if (typeof window === 'undefined') return {};

  try {
    const stored = localStorage.getItem(NAVIGATION_STORAGE_KEY);
    return stored ? JSON.parse(stored) : {};
  } catch {
    return {};
  }
}

// Save state to localStorage
function saveToStorage(state: NavigationState) {
  if (typeof window === 'undefined') return;

  try {
    localStorage.setItem(NAVIGATION_STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Ignore storage errors
  }
}

export const navigationState = writable<NavigationState>(loadFromStorage());

// Subscribe to store changes and persist them
navigationState.subscribe(state => {
  saveToStorage(state);
});

export const navigationActions = {
  // Track when we navigate to a page with context
  setContext(context: NavigationState['context'], metadata?: {
    jobId?: string;
    hostname?: string;
    previousRoute?: string;
  }) {
    navigationState.update(state => {
      const newState = {
        ...state,
        context,
        previousRoute: metadata?.previousRoute || state.previousRoute,
        jobId: metadata?.jobId,
        hostname: metadata?.hostname
      };
      console.log('Navigation setContext:', newState);
      return newState;
    });
  },

  // Set previous route for back navigation
  setPreviousRoute(route: string) {
    console.log('Setting previousRoute to:', route);
    navigationState.update(state => {
      const newState = {
        ...state,
        previousRoute: route
      };
      console.log('Updated navigationState:', newState);
      return newState;
    });
  },

  // Smart back navigation based on context
  goBack() {
    const stored = loadFromStorage();
    console.log('Navigation goBack called with stored state:', stored);

    // Store the route we're going back to
    const targetRoute = stored.previousRoute || this.getDefaultRoute(stored.context);
    console.log('Going back to:', targetRoute);

    // Set flag to skip next automatic update and clear previous route
    navigationState.update(state => ({
      ...state,
      previousRoute: undefined,
      skipNextUpdate: true
    }));

    // Navigate to the target route
    push(targetRoute);
  },

  // Get default route based on context
  getDefaultRoute(context?: string): string {
    switch (context) {
      case 'watcher':
        return '/watchers';
      case 'launch':
        return '/launch';
      case 'job':
        return '/';
      default:
        return '/';
    }
  },

  // Clear navigation state
  clear() {
    navigationState.set({});
    if (typeof window !== 'undefined') {
      localStorage.removeItem(NAVIGATION_STORAGE_KEY);
    }
  },

  // Get smart back label based on context
  getBackLabel(): string {
    const stored = loadFromStorage();

    if (stored.previousRoute) {
      if (stored.previousRoute === '/') return 'Jobs';
      if (stored.previousRoute === '/watchers') return 'Watchers';
      if (stored.previousRoute === '/launch') return 'Launch';
    }

    switch (stored.context) {
      case 'job':
        return 'Jobs';
      case 'watcher':
        return 'Watchers';
      case 'launch':
        return 'Launch';
      default:
        return 'Home';
    }
  }
};