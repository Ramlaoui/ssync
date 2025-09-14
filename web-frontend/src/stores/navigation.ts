import { writable, get } from 'svelte/store';
import { push } from 'svelte-spa-router';

interface NavigationState {
  previousRoute?: string;
  context?: 'job' | 'watcher' | 'home' | 'launch';
  jobId?: string;
  hostname?: string;
  breadcrumbs?: Array<{
    label: string;
    route: string;
  }>;
}

export const navigationState = writable<NavigationState>({});

export const navigationActions = {
  // Track when we navigate to a page with context
  setContext(context: NavigationState['context'], metadata?: {
    jobId?: string;
    hostname?: string;
    previousRoute?: string;
  }) {
    navigationState.update(state => ({
      ...state,
      context,
      previousRoute: metadata?.previousRoute || state.previousRoute,
      jobId: metadata?.jobId,
      hostname: metadata?.hostname
    }));
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
    const currentState = get(navigationState);

    console.log('Navigation goBack called with state:', currentState);

    // If we have a previous route, use it
    if (currentState.previousRoute) {
      console.log('Using previousRoute:', currentState.previousRoute);
      push(currentState.previousRoute);
      return;
    }

    // Fallback based on context
    console.log('Using context fallback:', currentState.context);
    switch (currentState.context) {
      case 'watcher':
        push('/watchers');
        break;
      case 'launch':
        push('/launch');
        break;
      case 'job':
        push('/jobs');
        break;
      default:
        push('/');
    }
  },

  // Clear navigation state
  clear() {
    navigationState.set({});
  },

  // Get smart back label based on context
  getBackLabel(): string {
    let label = 'Home';
    navigationState.subscribe(state => {
      switch (state.context) {
        case 'job':
          label = 'Back to Job';
          break;
        case 'watcher':
          label = 'Watchers';
          break;
        case 'launch':
          label = state.previousRoute?.includes('/job/') ? 'Back to Job' : 'Home';
          break;
        default:
          label = 'Home';
      }
    })();
    return label;
  }
};