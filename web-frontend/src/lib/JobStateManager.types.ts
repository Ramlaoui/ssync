/**
 * Dependency injection interfaces for JobStateManager
 * Allows for better testability by injecting mocked dependencies
 */

import type { AxiosInstance } from 'axios';
import type { Readable } from 'svelte/store';

/**
 * API client interface - can be mocked in tests
 */
export interface IApiClient {
  get<T = any>(url: string): Promise<{ data: T }>;
  post<T = any>(url: string, data?: any): Promise<{ data: T }>;
}

/**
 * WebSocket factory interface - creates WebSocket instances
 */
export interface IWebSocketFactory {
  create(url: string): WebSocket | MockWebSocket;
}

/**
 * Mock WebSocket interface for tests
 */
export interface MockWebSocket {
  readyState: number;
  url: string;
  onopen: ((event: Event) => void) | null;
  onclose: ((event: CloseEvent) => void) | null;
  onmessage: ((event: MessageEvent) => void) | null;
  onerror: ((event: Event) => void) | null;
  send(data: string): void;
  close(): void;
}

/**
 * Preferences interface
 */
export interface IPreferences {
  groupArrayJobs: boolean;
}

/**
 * Preferences store interface
 */
export interface IPreferencesStore extends Readable<IPreferences> {}

/**
 * Notification service interface
 */
export interface INotificationService {
  notify(options: { type: string; message: string; duration?: number }): void;
  notifyNewJob(jobId: string, hostname: string, state: string, name: string): void;
  notifyJobStateChange(jobId: string, hostname: string, oldState: string, newState: string): void;
}

/**
 * Environment interface - for testing DOM/window availability
 */
export interface IEnvironment {
  hasDocument: boolean;
  hasWindow: boolean;
  hasWebSocket: boolean;
  location?: {
    protocol: string;
    host: string;
  };
}

/**
 * All dependencies that JobStateManager needs
 */
export interface JobStateManagerDependencies {
  api: IApiClient;
  webSocketFactory: IWebSocketFactory;
  preferences: IPreferencesStore;
  notificationService: INotificationService;
  environment: IEnvironment;
}

/**
 * Production WebSocket factory
 */
export class ProductionWebSocketFactory implements IWebSocketFactory {
  create(url: string): WebSocket {
    return new WebSocket(url);
  }
}

/**
 * Production environment
 */
export class ProductionEnvironment implements IEnvironment {
  get hasDocument(): boolean {
    return typeof document !== 'undefined';
  }

  get hasWindow(): boolean {
    return typeof window !== 'undefined';
  }

  get hasWebSocket(): boolean {
    return typeof WebSocket !== 'undefined';
  }

  get location() {
    if (this.hasWindow) {
      return {
        protocol: window.location.protocol,
        host: window.location.host,
      };
    }
    return undefined;
  }
}
