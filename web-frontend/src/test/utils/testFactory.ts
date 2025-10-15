/**
 * Test factory for creating JobStateManager with mocked dependencies
 *
 * This factory provides fully controlled mock dependencies for testing
 * JobStateManager without making real network requests or accessing
 * the DOM.
 */

import { vi } from 'vitest';
import { writable } from 'svelte/store';
import { JobStateManager } from '../../lib/JobStateManager';
import type {
  JobStateManagerDependencies,
  IApiClient,
  IWebSocketFactory,
  IPreferencesStore,
  INotificationService,
  IEnvironment,
  MockWebSocket
} from '../../lib/JobStateManager.types';

/**
 * Create a mock API client
 */
export function createMockApiClient(): IApiClient {
  return {
    get: vi.fn().mockImplementation((url: string) => {
      // Mock /api/hosts endpoint
      if (url === '/api/hosts') {
        return Promise.resolve({
          data: [
            { hostname: 'cluster1.example.com', display_name: 'Cluster 1' },
            { hostname: 'cluster2.example.com', display_name: 'Cluster 2' },
          ]
        });
      }
      // Mock /api/status endpoint
      if (url.includes('/api/status')) {
        return Promise.resolve({
          data: {
            hostname: 'cluster1.example.com',
            jobs: [],
            timestamp: new Date().toISOString(),
            query_time: '0.123s',
            array_groups: [],
          }
        });
      }
      // Default response
      return Promise.resolve({ data: {} });
    }),
    post: vi.fn().mockResolvedValue({ data: {} }),
  };
}

/**
 * Create a mock WebSocket factory
 * Returns a factory that creates MockWebSocket instances
 */
export function createMockWebSocketFactory(): IWebSocketFactory & {
  instances: MockWebSocket[];
  getLastInstance: () => MockWebSocket | undefined;
} {
  const instances: MockWebSocket[] = [];

  const factory = {
    instances,
    getLastInstance() {
      return instances[instances.length - 1];
    },
    create(url: string): MockWebSocket {
      const ws: MockWebSocket = {
        url,
        readyState: 0, // CONNECTING
        onopen: null,
        onclose: null,
        onmessage: null,
        onerror: null,
        send: vi.fn(),
        close: vi.fn(() => {
          ws.readyState = 3; // CLOSED
          if (ws.onclose) {
            ws.onclose(new CloseEvent('close'));
          }
        }),
        simulateMessage: (data: any) => {
          if (ws.onmessage) {
            ws.onmessage(new MessageEvent('message', {
              data: JSON.stringify(data),
            }));
          }
        },
      };

      instances.push(ws);
      return ws;
    },
  };

  return factory;
}

/**
 * Create a mock preferences store
 */
export function createMockPreferencesStore(): IPreferencesStore {
  const store = writable({
    groupArrayJobs: true,
  });

  return {
    subscribe: store.subscribe,
  };
}

/**
 * Create a mock notification service
 */
export function createMockNotificationService(): INotificationService {
  return {
    notify: vi.fn(),
    notifyNewJob: vi.fn(),
    notifyJobStateChange: vi.fn(),
  };
}

/**
 * Create a mock environment
 *
 * @param options - Override default environment properties
 */
export function createMockEnvironment(options?: Partial<IEnvironment>): IEnvironment {
  return {
    hasDocument: false,
    hasWindow: false,
    hasWebSocket: true, // Enable WebSocket by default for tests
    location: {
      protocol: 'http:',
      host: 'localhost:3000',
    },
    ...options,
  };
}

/**
 * Create a fully mocked JobStateManager for testing
 *
 * This is the main test factory function. It creates a JobStateManager
 * with all dependencies mocked, so tests have full control over behavior.
 *
 * @param customDeps - Optional custom dependencies to override defaults
 * @returns Object containing the manager and all mock dependencies
 */
export function createTestJobStateManager(
  customDeps?: Partial<JobStateManagerDependencies>
) {
  // Create default mocks
  const api = customDeps?.api || createMockApiClient();
  const wsFactory = customDeps?.webSocketFactory || createMockWebSocketFactory();
  const preferences = customDeps?.preferences || createMockPreferencesStore();
  const notificationService = customDeps?.notificationService || createMockNotificationService();
  const environment = customDeps?.environment || createMockEnvironment();

  // Create manager with mocked dependencies
  const manager = new JobStateManager({
    api,
    webSocketFactory: wsFactory,
    preferences,
    notificationService,
    environment,
  });

  // Return both manager and mocks for test assertions
  return {
    manager,
    mocks: {
      api,
      wsFactory,
      preferences,
      notificationService,
      environment,
    },
  };
}

/**
 * Create a test manager without auto-initialization
 *
 * Useful for tests that want to control exactly when initialization happens
 */
export function createUninitializedTestManager() {
  return createTestJobStateManager({
    environment: createMockEnvironment({
      hasDocument: false,
      hasWindow: false,
      hasWebSocket: true,
    }),
  });
}

/**
 * Create a test manager with document/window available
 *
 * Useful for tests that need to test DOM interactions
 */
export function createTestManagerWithDOM() {
  return createTestJobStateManager({
    environment: createMockEnvironment({
      hasDocument: true,
      hasWindow: true,
      hasWebSocket: true,
      location: {
        protocol: 'http:',
        host: 'localhost:3000',
      },
    }),
  });
}

/**
 * Helper to simulate WebSocket opening after creation
 *
 * @param wsFactory - The mock WebSocket factory
 */
export function simulateWebSocketOpen(wsFactory: ReturnType<typeof createMockWebSocketFactory>) {
  const ws = wsFactory.getLastInstance();
  if (ws && ws.onopen) {
    ws.readyState = 1; // OPEN
    ws.onopen(new Event('open'));
  }
}

/**
 * Helper to simulate WebSocket message
 *
 * @param wsFactory - The mock WebSocket factory
 * @param data - The data to send
 */
export function simulateWebSocketMessage(
  wsFactory: ReturnType<typeof createMockWebSocketFactory>,
  data: any
) {
  const ws = wsFactory.getLastInstance();
  if (ws && ws.onmessage) {
    ws.onmessage(new MessageEvent('message', {
      data: JSON.stringify(data),
    }));
  }
}

/**
 * Helper to simulate WebSocket error
 *
 * @param wsFactory - The mock WebSocket factory
 */
export function simulateWebSocketError(wsFactory: ReturnType<typeof createMockWebSocketFactory>) {
  const ws = wsFactory.getLastInstance();
  if (ws && ws.onerror) {
    ws.onerror(new Event('error'));
  }
}

/**
 * Helper to simulate WebSocket close
 *
 * @param wsFactory - The mock WebSocket factory
 */
export function simulateWebSocketClose(wsFactory: ReturnType<typeof createMockWebSocketFactory>) {
  const ws = wsFactory.getLastInstance();
  if (ws) {
    ws.readyState = 3; // CLOSED
    if (ws.onclose) {
      ws.onclose(new CloseEvent('close'));
    }
  }
}

/**
 * Helper to wait for WebSocket to be created
 *
 * @param wsFactory - The mock WebSocket factory
 * @param timeout - Timeout in milliseconds (default: 1000)
 * @returns Promise that resolves to the MockWebSocket instance
 */
export function waitForWebSocket(
  wsFactory: ReturnType<typeof createMockWebSocketFactory>,
  timeout = 1000
): Promise<MockWebSocket> {
  return new Promise((resolve, reject) => {
    const startTime = Date.now();
    const check = () => {
      const ws = wsFactory.getLastInstance();
      if (ws) {
        resolve(ws);
      } else if (Date.now() - startTime > timeout) {
        reject(new Error('WebSocket creation timeout'));
      } else {
        setTimeout(check, 10);
      }
    };
    check();
  });
}
