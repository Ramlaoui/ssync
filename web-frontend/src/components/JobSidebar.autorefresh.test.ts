/**
 * JobSidebar Auto-refresh Integration Tests
 *
 * Simplified tests focusing on the core auto-refresh behavior:
 * - Jobs automatically update in the store (which the sidebar reactively displays)
 * - WebSocket messages trigger updates
 * - Polling works when WebSocket is unavailable
 * - State changes propagate automatically
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { get } from 'svelte/store';
import {
  createTestJobStateManager,
  simulateWebSocketOpen,
  simulateWebSocketClose,
  waitForWebSocket,
} from '../test/utils/testFactory';
import { setupMSW } from '../test/utils/mockApi';
import { createMockJob, mockJobs } from '../test/utils/mockData';
import type { JobStateManager } from '../lib/JobStateManager';

// Setup API mocking
setupMSW();

describe('JobSidebar - Auto-refresh Integration', () => {
  let manager: JobStateManager;
  let testSetup: ReturnType<typeof createTestJobStateManager>;

  beforeEach(() => {
    vi.useFakeTimers();
    testSetup = createTestJobStateManager();
    manager = testSetup.manager;
  });

  afterEach(() => {
    if (manager) {
      manager.destroy();
    }
    vi.useRealTimers();
    vi.clearAllTimers();
  });

  describe('Automatic Job State Updates', () => {
    it('should update job store when jobs are added (sidebar will reactively display)', async () => {
      // Start with no jobs
      let allJobs = get(manager.getAllJobs());
      expect(allJobs.length).toBe(0);

      // Add a running job
      const job = createMockJob({
        job_id: 'auto-1',
        hostname: 'test.com',
        state: 'R',
        name: 'Auto Update Test',
      });

      manager['queueUpdate']({
        jobId: job.job_id,
        hostname: job.hostname,
        job,
        source: 'api',
        timestamp: Date.now(),
        priority: 'normal',
      }, true);

      await vi.advanceTimersByTimeAsync(100);

      // Job should be in store (sidebar will display it reactively)
      allJobs = get(manager.getAllJobs());
      expect(allJobs.length).toBe(1);
      expect(allJobs[0].job_id).toBe('auto-1');
      expect(allJobs[0].state).toBe('R');
    });

    it('should update job states automatically (PD → R → CD)', async () => {
      // Add pending job
      const job = createMockJob({
        job_id: 'state-transition',
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
      expect(allJobs[0].state).toBe('PD');

      // Transition to running
      manager['queueUpdate']({
        jobId: job.job_id,
        hostname: job.hostname,
        job: { ...job, state: 'R' },
        source: 'api',
        timestamp: Date.now() + 1000,
        priority: 'normal',
      }, true);

      await vi.advanceTimersByTimeAsync(100);

      allJobs = get(manager.getAllJobs());
      expect(allJobs[0].state).toBe('R');

      // Transition to completed
      manager['queueUpdate']({
        jobId: job.job_id,
        hostname: job.hostname,
        job: { ...job, state: 'CD' },
        source: 'api',
        timestamp: Date.now() + 2000,
        priority: 'normal',
      }, true);

      await vi.advanceTimersByTimeAsync(100);

      allJobs = get(manager.getAllJobs());
      expect(allJobs[0].state).toBe('CD');
    });

    it('should update multiple jobs concurrently', async () => {
      // Add 3 pending jobs
      const jobs = Array.from({ length: 3 }, (_, i) =>
        createMockJob({
          job_id: `concurrent-${i}`,
          hostname: 'test.com',
          state: 'PD',
        })
      );

      jobs.forEach(job => {
        manager['queueUpdate']({
          jobId: job.job_id,
          hostname: job.hostname,
          job,
          source: 'api',
          timestamp: Date.now(),
          priority: 'normal',
        }, false); // Batch them
      });

      await vi.advanceTimersByTimeAsync(300);

      // All jobs should be in store
      let allJobs = get(manager.getAllJobs());
      expect(allJobs.length).toBe(3);

      // Update all to running
      jobs.forEach(job => {
        manager['queueUpdate']({
          jobId: job.job_id,
          hostname: job.hostname,
          job: { ...job, state: 'R' },
          source: 'api',
          timestamp: Date.now() + 1000,
          priority: 'normal',
        }, false);
      });

      await vi.advanceTimersByTimeAsync(300);

      // All should be running
      allJobs = get(manager.getAllJobs());
      allJobs.forEach(job => {
        expect(job.state).toBe('R');
      });
    });
  });

  describe('WebSocket Real-time Updates', () => {
    it('should receive WebSocket updates and update store', async () => {
      // Connect WebSocket
      manager.connectWebSocket();
      const ws = await waitForWebSocket(testSetup.mocks.wsFactory);
      simulateWebSocketOpen(testSetup.mocks.wsFactory);

      await vi.advanceTimersByTimeAsync(100);

      // Send job update via WebSocket
      const job = createMockJob({
        job_id: 'ws-realtime',
        hostname: 'test.com',
        state: 'R',
        name: 'WebSocket Job',
      });

      ws.simulateMessage({
        type: 'job_update',
        job_id: job.job_id,
        hostname: job.hostname,
        job,
      });

      await vi.advanceTimersByTimeAsync(300);

      // Job should be in store
      const allJobs = get(manager.getAllJobs());
      const wsJob = allJobs.find(j => j.job_id === 'ws-realtime');
      expect(wsJob).toBeDefined();
      expect(wsJob?.state).toBe('R');
    });

    it('should handle WebSocket state_change messages', async () => {
      // Add initial pending job
      const job = createMockJob({
        job_id: 'ws-state-change',
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

      // Connect WebSocket
      manager.connectWebSocket();
      const ws = await waitForWebSocket(testSetup.mocks.wsFactory);
      simulateWebSocketOpen(testSetup.mocks.wsFactory);

      await vi.advanceTimersByTimeAsync(100);

      // Send state change
      ws.simulateMessage({
        type: 'state_change',
        job_id: job.job_id,
        hostname: job.hostname,
        job: { ...job, state: 'R' },
      });

      await vi.advanceTimersByTimeAsync(300);

      // State should be updated
      const allJobs = get(manager.getAllJobs());
      const updatedJob = allJobs.find(j => j.job_id === 'ws-state-change');
      expect(updatedJob?.state).toBe('R');
    });

    it('should handle batch WebSocket updates', async () => {
      // Connect WebSocket
      manager.connectWebSocket();
      const ws = await waitForWebSocket(testSetup.mocks.wsFactory);
      simulateWebSocketOpen(testSetup.mocks.wsFactory);

      await vi.advanceTimersByTimeAsync(100);

      // Send batch update with 5 jobs
      const batchJobs = Array.from({ length: 5 }, (_, i) =>
        createMockJob({
          job_id: `batch-${i}`,
          hostname: 'test.com',
          state: 'R',
        })
      );

      ws.simulateMessage({
        type: 'batch_update',
        updates: batchJobs.map(job => ({
          job_id: job.job_id,
          hostname: job.hostname,
          job,
        })),
      });

      await vi.advanceTimersByTimeAsync(300);

      // All batch jobs should be in store
      const allJobs = get(manager.getAllJobs());
      const batchJobsInStore = allJobs.filter(j => j.job_id.startsWith('batch-'));
      expect(batchJobsInStore.length).toBe(5);
    });
  });

  describe('Polling-based Auto-refresh', () => {
    it('should start polling when WebSocket is unavailable', async () => {
      // Connect then disconnect WebSocket
      manager.connectWebSocket();
      const ws = await waitForWebSocket(testSetup.mocks.wsFactory);
      simulateWebSocketOpen(testSetup.mocks.wsFactory);
      await vi.advanceTimersByTimeAsync(100);

      simulateWebSocketClose(testSetup.mocks.wsFactory);
      await vi.advanceTimersByTimeAsync(1000);

      // Should be polling now
      const state = get(manager.getState());
      expect(state.pollingActive).toBe(true);
      expect(state.wsConnected).toBe(false);
    });

    it('should fetch and display updated job states from polling source', async () => {
      // Initial state: API returns a PENDING job
      testSetup.mocks.api.setResponse('/api/status', {
        hostname: 'test.com',
        jobs: [
          createMockJob({ job_id: 'poll-state-change', state: 'PD', hostname: 'test.com', name: 'Polling Test' }),
        ],
        timestamp: new Date().toISOString(),
        query_time: '0.123s',
        array_groups: [],
      });

      // Disable WebSocket to force polling
      manager.connectWebSocket();
      const ws = await waitForWebSocket(testSetup.mocks.wsFactory);
      simulateWebSocketClose(testSetup.mocks.wsFactory);

      await vi.advanceTimersByTimeAsync(1000);

      // Initial sync to get the pending job
      await manager.syncAllHosts();
      await vi.advanceTimersByTimeAsync(500);

      // Verify initial state
      let allJobs = get(manager.getAllJobs());
      let pollJob = allJobs.find(j => j.job_id === 'poll-state-change');
      expect(pollJob?.state).toBe('PD');

      // SIMULATE EXTERNAL CHANGE: Job now running on the cluster
      // Update the mock API to return the job in RUNNING state
      testSetup.mocks.api.setResponse('/api/status', {
        hostname: 'test.com',
        jobs: [
          createMockJob({ job_id: 'poll-state-change', state: 'R', hostname: 'test.com', name: 'Polling Test', runtime: '00:05:00' }),
        ],
        timestamp: new Date().toISOString(),
        query_time: '0.123s',
        array_groups: [],
      });

      // Wait for cache to expire and next poll to happen
      await vi.advanceTimersByTimeAsync(61000); // 61 seconds for cache expiry + poll

      // Trigger sync (polling would do this automatically)
      await manager.syncAllHosts();
      await vi.advanceTimersByTimeAsync(500);

      // Verify the state was updated from the polling source
      allJobs = get(manager.getAllJobs());
      pollJob = allJobs.find(j => j.job_id === 'poll-state-change');
      expect(pollJob?.state).toBe('R');
      expect(pollJob?.runtime).toBe('00:05:00');
    });

    it('should continue polling and updating as job progresses through states', async () => {
      // Start with PENDING
      testSetup.mocks.api.setResponse('/api/status', {
        hostname: 'test.com',
        jobs: [
          createMockJob({ job_id: 'poll-lifecycle', state: 'PD', hostname: 'test.com' }),
        ],
        timestamp: new Date().toISOString(),
        query_time: '0.123s',
        array_groups: [],
      });

      // Disable WebSocket
      manager.connectWebSocket();
      const ws = await waitForWebSocket(testSetup.mocks.wsFactory);
      simulateWebSocketClose(testSetup.mocks.wsFactory);
      await vi.advanceTimersByTimeAsync(1000);

      // Initial sync
      await manager.syncAllHosts();
      await vi.advanceTimersByTimeAsync(500);

      let allJobs = get(manager.getAllJobs());
      expect(allJobs.find(j => j.job_id === 'poll-lifecycle')?.state).toBe('PD');

      // Job becomes RUNNING
      testSetup.mocks.api.setResponse('/api/status', {
        hostname: 'test.com',
        jobs: [
          createMockJob({ job_id: 'poll-lifecycle', state: 'R', hostname: 'test.com' }),
        ],
        timestamp: new Date().toISOString(),
        query_time: '0.123s',
        array_groups: [],
      });

      await vi.advanceTimersByTimeAsync(61000);
      await manager.syncAllHosts();
      await vi.advanceTimersByTimeAsync(500);

      allJobs = get(manager.getAllJobs());
      expect(allJobs.find(j => j.job_id === 'poll-lifecycle')?.state).toBe('R');

      // Job COMPLETES
      testSetup.mocks.api.setResponse('/api/status', {
        hostname: 'test.com',
        jobs: [
          createMockJob({ job_id: 'poll-lifecycle', state: 'CD', hostname: 'test.com' }),
        ],
        timestamp: new Date().toISOString(),
        query_time: '0.123s',
        array_groups: [],
      });

      await vi.advanceTimersByTimeAsync(61000);
      await manager.syncAllHosts();
      await vi.advanceTimersByTimeAsync(500);

      allJobs = get(manager.getAllJobs());
      expect(allJobs.find(j => j.job_id === 'poll-lifecycle')?.state).toBe('CD');
    });
  });

  describe('Job Store Reactivity (for Sidebar Display)', () => {
    it('should provide reactive stores that sidebar can subscribe to', () => {
      // Get stores
      const allJobs = manager.getAllJobs();
      const runningJobs = manager.getJobsByState('R');
      const pendingJobs = manager.getJobsByState('PD');

      // All should be subscribable stores
      expect(typeof allJobs.subscribe).toBe('function');
      expect(typeof runningJobs.subscribe).toBe('function');
      expect(typeof pendingJobs.subscribe).toBe('function');
    });

    it('should update derived stores when job states change', async () => {
      // Subscribe to running and pending stores
      const runningJobs = manager.getJobsByState('R');
      const pendingJobs = manager.getJobsByState('PD');

      // Add pending job
      const job = createMockJob({
        job_id: 'derived-test',
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

      await vi.advanceTimersByTimeAsync(100);

      // Should be in pending store
      expect(get(pendingJobs).length).toBe(1);
      expect(get(runningJobs).length).toBe(0);

      // Change to running
      manager['queueUpdate']({
        jobId: job.job_id,
        hostname: job.hostname,
        job: { ...job, state: 'R' },
        source: 'api',
        timestamp: Date.now() + 1000,
        priority: 'normal',
      }, true);

      await vi.advanceTimersByTimeAsync(100);

      // Should move to running store
      expect(get(runningJobs).length).toBe(1);
      expect(get(pendingJobs).length).toBe(0);
    });
  });
});
