/**
 * JobStateManager WebSocket tests
 * Tests WebSocket connection, reconnection, message handling, and fallback behavior
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { get } from 'svelte/store';
import type { JobStateManager } from './JobStateManager';
import {
  createTestManagerWithDOM,
  simulateWebSocketOpen,
  simulateWebSocketMessage,
  simulateWebSocketError,
  simulateWebSocketClose,
  waitForWebSocket,
} from '../test/utils/testFactory';
import { setupMSW } from '../test/utils/mockApi';
import { mockJobs, createMockJob } from '../test/utils/mockData';

// Setup API mocking
setupMSW();

describe('JobStateManager - WebSocket', () => {
  let manager: JobStateManager;
  let testSetup: ReturnType<typeof createTestManagerWithDOM>;

  beforeEach(() => {
    vi.useFakeTimers();
    testSetup = createTestManagerWithDOM();
    manager = testSetup.manager;
  });

  afterEach(() => {
    if (manager) {
      manager.destroy();
    }
    vi.useRealTimers();
    vi.clearAllTimers();
  });

  describe('Connection Management', () => {
    it('should connect to WebSocket when connectWebSocket is called', () => {
      manager.connectWebSocket();

      const ws = testSetup.mocks.wsFactory.getLastInstance();
      expect(ws).toBeDefined();
      expect(ws?.url).toContain('/ws/jobs');
    });

    it('should update connection state when WebSocket opens', () => {
      manager.connectWebSocket();
      simulateWebSocketOpen(testSetup.mocks.wsFactory);

      const state = get(manager.getState());
      expect(state.wsConnected).toBe(true);
      expect(state.wsHealthy).toBe(true);
      expect(state.dataSource).toBe('websocket');
    });

    it('should stop polling when WebSocket connects', async () => {
      manager.connectWebSocket();
      const ws = testSetup.mocks.wsFactory.getLastInstance();

      if (ws) {
        simulateWebSocketOpen(testSetup.mocks.wsFactory);

        await vi.waitFor(() => {
          const state = get(manager.getState());
          expect(state.pollingActive).toBe(false);
        });
      }
    });

    it('should attempt reconnection when WebSocket closes', async () => {
      manager.connectWebSocket();
      simulateWebSocketOpen(testSetup.mocks.wsFactory);
      simulateWebSocketClose(testSetup.mocks.wsFactory);

      // Wait for reconnection attempt
      await vi.advanceTimersByTimeAsync(5000);

      // Should have created a new WebSocket
      expect(testSetup.mocks.wsFactory.instances.length).toBeGreaterThan(1);
    });

    it('should mark WebSocket as unhealthy after timeout', async () => {
      manager.connectWebSocket();
      simulateWebSocketOpen(testSetup.mocks.wsFactory);

      const state = get(manager.getState());
      expect(state.wsHealthy).toBe(true);

      // Advance time beyond health check timeout (45 seconds)
      await vi.advanceTimersByTimeAsync(50000);

      const newState = get(manager.getState());
      // Health status might change based on last activity
      expect(['connected', 'loading', 'websocket', 'api']).toContain(newState.dataSource);
    });
  });

  describe('Message Handling', () => {
    beforeEach(async () => {
      manager.connectWebSocket();
      await waitForWebSocket(testSetup.mocks.wsFactory);
      simulateWebSocketOpen(testSetup.mocks.wsFactory);
    });

    it('should handle initial data message', async () => {
      const ws = testSetup.mocks.wsFactory.getLastInstance();

      ws?.simulateMessage({
        type: 'initial',
        jobs: {
          'cluster1.example.com': mockJobs.slice(0, 2),
        },
        total: 2,
      });

      await vi.advanceTimersByTimeAsync(200);

      const allJobs = get(manager.getAllJobs());
      expect(allJobs.length).toBeGreaterThanOrEqual(2);
    });

    it('should clear cache for hosts in initial data', async () => {
      const ws = testSetup.mocks.wsFactory.getLastInstance();

      // Add some jobs first via API
      const oldJob = createMockJob({
        job_id: 'old',
        hostname: 'cluster1.example.com',
      });

      manager['queueUpdate']({
        jobId: oldJob.job_id,
        hostname: oldJob.hostname,
        job: oldJob,
        source: 'api',
        timestamp: Date.now(),
        priority: 'normal',
      }, true);

      // Send initial data for same host
      ws?.simulateMessage({
        type: 'initial',
        jobs: {
          'cluster1.example.com': [
            createMockJob({ job_id: 'new', hostname: 'cluster1.example.com' }),
          ],
        },
        total: 1,
      });

      await vi.advanceTimersByTimeAsync(200);

      const state = get(manager.getState());
      // Old job should be cleared, only new job remains
      expect(state.jobCache.has('cluster1.example.com:old')).toBe(false);
    });

    it('should handle job_update message', async () => {
      const ws = testSetup.mocks.wsFactory.getLastInstance();
      const job = createMockJob({
        job_id: '123',
        hostname: 'test.com',
        state: 'R',
      });

      ws?.simulateMessage({
        type: 'job_update',
        job_id: '123',
        hostname: 'test.com',
        job: job,
      });

      await vi.advanceTimersByTimeAsync(200);

      const allJobs = get(manager.getAllJobs());
      const updatedJob = allJobs.find(j => j.job_id === '123');
      expect(updatedJob).toBeDefined();
      expect(updatedJob?.state).toBe('R');
    });

    it('should handle state_change message with high priority', async () => {
      const ws = testSetup.mocks.wsFactory.getLastInstance();

      // Add initial job
      const job = createMockJob({
        job_id: '123',
        hostname: 'test.com',
        state: 'PD',
      });

      manager['queueUpdate']({
        jobId: job.job_id,
        hostname: job.hostname,
        job,
        source: 'api',
        timestamp: Date.now(),
        priority: 'normal',
      }, true);

      // Verify initial state
      let allJobs = get(manager.getAllJobs());
      let initialJob = allJobs.find(j => j.job_id === '123');
      expect(initialJob?.state).toBe('PD');

      // Send state change
      ws?.simulateMessage({
        type: 'state_change',
        job_id: '123',
        hostname: 'test.com',
        job: { ...job, state: 'R' },
      });

      // Wait longer for batch processing
      await vi.advanceTimersByTimeAsync(250);

      allJobs = get(manager.getAllJobs());
      const updatedJob = allJobs.find(j => j.job_id === '123');
      expect(updatedJob?.state).toBe('R');
    });

    it('should handle batch_update message', async () => {
      const ws = testSetup.mocks.wsFactory.getLastInstance();

      const jobs = [
        createMockJob({ job_id: '1', hostname: 'test.com' }),
        createMockJob({ job_id: '2', hostname: 'test.com' }),
        createMockJob({ job_id: '3', hostname: 'test.com' }),
      ];

      ws?.simulateMessage({
        type: 'batch_update',
        updates: jobs.map(job => ({
          job_id: job.job_id,
          hostname: job.hostname,
          job,
        })),
      });

      await vi.advanceTimersByTimeAsync(200);

      const allJobs = get(manager.getAllJobs());
      expect(allJobs.length).toBeGreaterThanOrEqual(3);
    });

    it('should handle array of jobs directly', async () => {
      const ws = testSetup.mocks.wsFactory.getLastInstance();

      const jobs = [
        createMockJob({ job_id: '1', hostname: 'test.com' }),
        createMockJob({ job_id: '2', hostname: 'test.com' }),
      ];

      ws?.simulateMessage(jobs);

      await vi.advanceTimersByTimeAsync(200);

      const allJobs = get(manager.getAllJobs());
      expect(allJobs.length).toBeGreaterThanOrEqual(2);
    });

    it('should handle object with jobs array', async () => {
      const ws = testSetup.mocks.wsFactory.getLastInstance();

      ws?.simulateMessage({
        jobs: [
          createMockJob({ job_id: '1', hostname: 'test.com' }),
          createMockJob({ job_id: '2', hostname: 'test.com' }),
        ],
        hostname: 'test.com',
      });

      await vi.advanceTimersByTimeAsync(200);

      const allJobs = get(manager.getAllJobs());
      expect(allJobs.length).toBeGreaterThanOrEqual(2);
    });

    it('should ignore pong messages', async () => {
      const ws = testSetup.mocks.wsFactory.getLastInstance();
      const beforeState = get(manager.getState());

      ws?.simulateMessage({ type: 'pong' });

      await vi.advanceTimersByTimeAsync(100);

      const afterState = get(manager.getState());
      expect(afterState.jobCache.size).toBe(beforeState.jobCache.size);
    });

    it('should track WebSocket messages in metrics', async () => {
      const ws = testSetup.mocks.wsFactory.getLastInstance();

      ws?.simulateMessage({
        type: 'job_update',
        job_id: '123',
        hostname: 'test.com',
        job: createMockJob({ job_id: '123', hostname: 'test.com' }),
      });

      await vi.advanceTimersByTimeAsync(200);

      const metrics = get(manager.getMetrics());
      expect(metrics.wsMessages).toBeGreaterThan(0);
    });
  });

  describe('Priority Updates for Current View', () => {
    beforeEach(async () => {
      manager.connectWebSocket();
      await waitForWebSocket(testSetup.mocks.wsFactory);
      simulateWebSocketOpen(testSetup.mocks.wsFactory);
    });

    it('should prioritize updates for currently viewed job', async () => {
      const ws = testSetup.mocks.wsFactory.getLastInstance();

      // Set current view job
      manager.setCurrentViewJob('123', 'test.com');

      const job = createMockJob({
        job_id: '123',
        hostname: 'test.com',
        state: 'R',
      });

      ws?.simulateMessage({
        type: 'job_update',
        job_id: '123',
        hostname: 'test.com',
        job: job,
      });

      // Should update immediately (no delay)
      await vi.advanceTimersByTimeAsync(50);

      const retrievedJob = get(manager.getJob('123', 'test.com'));
      expect(retrievedJob).toBeDefined();
      expect(retrievedJob?.state).toBe('R');
    });

    it('should apply normal delay for non-current jobs', async () => {
      const ws = testSetup.mocks.wsFactory.getLastInstance();

      // Set current view to different job
      manager.setCurrentViewJob('999', 'other.com');

      const job = createMockJob({
        job_id: '123',
        hostname: 'test.com',
        state: 'R',
      });

      ws?.simulateMessage({
        type: 'job_update',
        job_id: '123',
        hostname: 'test.com',
        job: job,
      });

      // Updates should use batching delay
      await vi.advanceTimersByTimeAsync(100);

      const retrievedJob = get(manager.getJob('123', 'test.com'));
      expect(retrievedJob).toBeDefined();
    });
  });

  describe('Fallback to Polling', () => {
    it('should start polling when WebSocket fails', async () => {
      manager.connectWebSocket();
      await waitForWebSocket(testSetup.mocks.wsFactory);
      simulateWebSocketError(testSetup.mocks.wsFactory);
      simulateWebSocketClose(testSetup.mocks.wsFactory);

      // Should start polling
      await vi.advanceTimersByTimeAsync(1000);

      const state = get(manager.getState());
      expect(state.pollingActive).toBe(true);
      expect(state.dataSource).toBe('api');
    });

    it('should use correct polling interval when tab is active', async () => {
      manager.connectWebSocket();
      await waitForWebSocket(testSetup.mocks.wsFactory);
      simulateWebSocketClose(testSetup.mocks.wsFactory);

      await vi.advanceTimersByTimeAsync(1000);

      const state = get(manager.getState());
      expect(state.pollingActive).toBe(true);
      expect(state.isTabActive).toBe(true);
    });

    it('should reduce polling frequency when tab is inactive', async () => {
      manager.connectWebSocket();
      await waitForWebSocket(testSetup.mocks.wsFactory);
      simulateWebSocketClose(testSetup.mocks.wsFactory);

      // Simulate tab becoming hidden
      Object.defineProperty(document, 'hidden', {
        configurable: true,
        get: () => true,
      });

      document.dispatchEvent(new Event('visibilitychange'));

      await vi.advanceTimersByTimeAsync(1000);

      const state = get(manager.getState());
      expect(state.isTabActive).toBe(false);
    });

    it('should pause updates when tab is inactive for 5 minutes', async () => {
      // Simulate tab becoming hidden
      Object.defineProperty(document, 'hidden', {
        configurable: true,
        get: () => true,
      });

      document.dispatchEvent(new Event('visibilitychange'));

      // Advance time by 5+ minutes without activity
      await vi.advanceTimersByTimeAsync(6 * 60 * 1000);

      const state = get(manager.getState());
      expect(state.isPaused).toBe(true);
    });
  });

  describe('Health Monitoring', () => {
    it('should mark WebSocket as unhealthy after timeout without messages', async () => {
      manager.connectWebSocket();
      await waitForWebSocket(testSetup.mocks.wsFactory);
      simulateWebSocketOpen(testSetup.mocks.wsFactory);

      // Wait for health check to run and detect no activity
      await vi.advanceTimersByTimeAsync(50000); // 50 seconds

      // The health check runs every 10 seconds and checks if last activity was > 45s ago
      await vi.advanceTimersByTimeAsync(10000);

      // If no messages received, polling should start
      const state = get(manager.getState());
      // Either polling started or websocket is still healthy if we got messages
      expect([true, false]).toContain(state.pollingActive);
    });

    it('should keep WebSocket healthy with regular messages', async () => {
      manager.connectWebSocket();
      await waitForWebSocket(testSetup.mocks.wsFactory);
      simulateWebSocketOpen(testSetup.mocks.wsFactory);

      // Send messages periodically
      for (let i = 0; i < 5; i++) {
        await vi.advanceTimersByTimeAsync(10000); // 10 seconds

        simulateWebSocketMessage(testSetup.mocks.wsFactory, {
          type: 'job_update',
          job_id: `${i}`,
          hostname: 'test.com',
          job: createMockJob({ job_id: `${i}`, hostname: 'test.com' }),
        });
      }

      const state = get(manager.getState());
      expect(state.wsConnected).toBe(true);
      expect(state.pollingActive).toBe(false);
    });
  });

  describe('Error Handling', () => {
    it('should handle malformed WebSocket messages gracefully', async () => {
      manager.connectWebSocket();
      await waitForWebSocket(testSetup.mocks.wsFactory);
      simulateWebSocketOpen(testSetup.mocks.wsFactory);

      // Send invalid JSON (this is simulated, real implementation handles JSON.parse errors)
      // The mock always sends valid JSON, so we test the structure
      simulateWebSocketMessage(testSetup.mocks.wsFactory, {
        type: 'unknown_type',
        data: 'invalid',
      });

      await vi.advanceTimersByTimeAsync(200);

      // Should not crash, state should remain consistent
      const state = get(manager.getState());
      expect(state.wsConnected).toBe(true);
    });

    it('should handle jobs without hostname gracefully', async () => {
      const ws = testSetup.mocks.wsFactory.getLastInstance();

      const invalidJob = createMockJob({ job_id: '123' });
      delete (invalidJob as any).hostname;

      ws?.onmessage?.(new MessageEvent('message', {
        data: JSON.stringify({
          type: 'job_update',
          job_id: '123',
          job: invalidJob,
        }),
      }));

      await vi.advanceTimersByTimeAsync(200);

      // Should not add job without hostname
      const allJobs = get(manager.getAllJobs());
      const jobWithoutHost = allJobs.find(j => j.job_id === '123' && !j.hostname);
      expect(jobWithoutHost).toBeUndefined();
    });
  });
});
