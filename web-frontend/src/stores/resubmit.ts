import { writable, get } from 'svelte/store';

export interface ResubmitData {
  scriptContent: string;
  hostname: string;
  workDir?: string;  // Remote working directory on cluster
  localSourceDir?: string;  // Local source directory that was synced
  originalJobId: string;
  jobName?: string;
  submitLine?: string;
  watcherVariables?: Record<string, string>;  // Captured variables from watchers
  watchers?: Array<{  // Full watcher configurations
    name: string;
    type: string;
    actions: any[];
    variables?: Record<string, string>;
    status?: string;
    created_at?: string;
  }>;
}

function createResubmitStore() {
  const store = writable<ResubmitData | null>(null);
  const { subscribe, set, update } = store;

  return {
    subscribe,
    setResubmitData: (data: ResubmitData) => {
      console.log('Setting resubmit data in store:', data);
      set(data);
    },
    clear: () => {
      set(null);
    },
    consumeResubmitData: () => {
      const data = get(store);
      console.log('Consuming resubmit data from store:', data);
      if (data) {
        set(null); // Clear after consuming
      }
      return data;
    },
    getResubmitData: () => {
      return get(store);
    }
  };
}

export const resubmitStore = createResubmitStore();