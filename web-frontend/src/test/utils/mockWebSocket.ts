/**
 * WebSocket mocking utilities
 */

import { vi } from 'vitest';

export class MockWebSocket {
  url: string;
  readyState: number = WebSocket.CONNECTING;
  onopen: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;

  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  constructor(url: string) {
    this.url = url;
  }

  send(data: string): void {
    // Mock send implementation
  }

  close(): void {
    this.readyState = WebSocket.CLOSED;
    if (this.onclose) {
      this.onclose(new CloseEvent('close'));
    }
  }

  // Test helpers
  simulateOpen(): void {
    this.readyState = WebSocket.OPEN;
    if (this.onopen) {
      this.onopen(new Event('open'));
    }
  }

  simulateMessage(data: any): void {
    if (this.onmessage) {
      this.onmessage(new MessageEvent('message', {
        data: JSON.stringify(data),
      }));
    }
  }

  simulateError(): void {
    if (this.onerror) {
      this.onerror(new Event('error'));
    }
  }

  simulateClose(): void {
    this.readyState = WebSocket.CLOSED;
    if (this.onclose) {
      this.onclose(new CloseEvent('close'));
    }
  }
}

/**
 * Setup WebSocket mock for tests
 */
export function setupWebSocketMock(): {
  WebSocketMock: typeof MockWebSocket;
  getLastInstance: () => MockWebSocket | undefined;
  getAllInstances: () => MockWebSocket[];
} {
  const instances: MockWebSocket[] = [];

  const WebSocketMock = vi.fn().mockImplementation((url: string) => {
    const instance = new MockWebSocket(url);
    instances.push(instance);
    return instance;
  }) as any;

  // Copy static properties
  WebSocketMock.CONNECTING = 0;
  WebSocketMock.OPEN = 1;
  WebSocketMock.CLOSING = 2;
  WebSocketMock.CLOSED = 3;

  global.WebSocket = WebSocketMock;

  return {
    WebSocketMock,
    getLastInstance: () => instances[instances.length - 1],
    getAllInstances: () => instances,
  };
}

/**
 * Wait for WebSocket to be created
 */
export function waitForWebSocket(
  getInstances: () => MockWebSocket[],
  timeout = 1000
): Promise<MockWebSocket> {
  return new Promise((resolve, reject) => {
    const startTime = Date.now();
    const check = () => {
      const instances = getInstances();
      if (instances.length > 0) {
        resolve(instances[instances.length - 1]);
      } else if (Date.now() - startTime > timeout) {
        reject(new Error('WebSocket creation timeout'));
      } else {
        setTimeout(check, 10);
      }
    };
    check();
  });
}
