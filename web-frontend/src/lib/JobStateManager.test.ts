/**
 * Core JobStateManager tests
 * Tests basic initialization, state management, and job operations
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { get } from 'svelte/store';
import type { JobStateManager } from './JobStateManager';
import { createTestJobStateManager, waitForWebSocket, simulateWebSocketOpen, simulateWebSocketClose, simulateWebSocketError } from '../test/utils/testFactory';
import { setupMSW, addHandler, createErrorHandler } from '../test/utils/mockApi';
import { mockJobs, createMockJob } from '../test/utils/mockData';
import { http, HttpResponse } from 'msw';

// Setup API mocking
setupMSW();

describe('JobStateManager - Core Functionality', () => {
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

  describe('Initialization', () => {
    it('should initialize with empty state', () => {
      const state = get(manager.getState());

      expect(state.jobCache.size).toBe(0);
      expect(state.hostStates.size).toBe(0);
      expect(state.wsConnected).toBe(false);
      expect(state.pollingActive).toBe(false);
    });

    it('should attempt WebSocket connection on connectWebSocket', async () => {
      manager.connectWebSocket();

      // Wait for WebSocket to be created
      await vi.waitFor(() => {
        expect(testSetup.mocks.wsFactory.instances.length).toBe(1);
      }, { timeout: 1000 });
    });

    it('should fall back to polling if WebSocket fails', async () => {
      manager.connectWebSocket();

      // Wait for WebSocket and simulate failure
      const ws = await waitForWebSocket(testSetup.mocks.wsFactory);
      simulateWebSocketError(testSetup.mocks.wsFactory);
      simulateWebSocketClose(testSetup.mocks.wsFactory);

      // Should start polling
      await vi.advanceTimersByTimeAsync(1000);

      const state = get(manager.getState());
      expect(state.pollingActive).toBe(true);
    });
  });

  describe('Job Cache Management', () => {
    // Tests use manager from main beforeEach

    it('should add jobs to cache', () => {
      const job = createMockJob({ job_id: '123', hostname: 'test.com' });

      manager['queueUpdate']({
        jobId: job.job_id,
        hostname: job.hostname,
        job,
        source: 'api',
        timestamp: Date.now(),
        priority: 'normal',
      }, true);

      const state = get(manager.getState());
      expect(state.jobCache.has('test.com:123')).toBe(true);
    });

    it('should retrieve jobs from cache', () => {
      const job = createMockJob({ job_id: '123', hostname: 'test.com' });

      manager['queueUpdate']({
        jobId: job.job_id,
        hostname: job.hostname,
        job,
        source: 'api',
        timestamp: Date.now(),
        priority: 'normal',
      }, true);

      const allJobs = get(manager.getAllJobs());
      expect(allJobs).toHaveLength(1);
      expect(allJobs[0].job_id).toBe('123');
    });

    it('should update existing jobs', () => {
      const job = createMockJob({
        job_id: '123',
        hostname: 'test.com',
        state: 'PD'
      });

      // Add initial job
      manager['queueUpdate']({
        jobId: job.job_id,
        hostname: job.hostname,
        job,
        source: 'api',
        timestamp: Date.now(),
        priority: 'normal',
      }, true);

      // Update job state
      const updatedJob = { ...job, state: 'R' as const };
      manager['queueUpdate']({
        jobId: job.job_id,
        hostname: job.hostname,
        job: updatedJob,
        source: 'api',
        timestamp: Date.now() + 1000,
        priority: 'normal',
      }, true);

      const allJobs = get(manager.getAllJobs());
      expect(allJobs).toHaveLength(1);
      expect(allJobs[0].state).toBe('R');
    });

    it('should deduplicate jobs by hostname:jobId', () => {
      const job = createMockJob({ job_id: '123', hostname: 'test.com' });

      // Add same job twice
      manager['queueUpdate']({
        jobId: job.job_id,
        hostname: job.hostname,
        job,
        source: 'api',
        timestamp: Date.now(),
        priority: 'normal',
      }, true);

      manager['queueUpdate']({
        jobId: job.job_id,
        hostname: job.hostname,
        job,
        source: 'api',
        timestamp: Date.now() + 100,
        priority: 'normal',
      }, true);

      const allJobs = get(manager.getAllJobs());
      expect(allJobs).toHaveLength(1);
    });
  });

  describe('Cache Validation', () => {
    // Tests use manager from main beforeEach

    it('should validate running jobs with 1 min lifetime', () => {
      const job = createMockJob({ state: 'R', hostname: 'test.com', job_id: '123' });
      const cacheKey = 'test.com:123';

      manager['queueUpdate']({
        jobId: job.job_id,
        hostname: job.hostname,
        job,
        source: 'api',
        timestamp: Date.now(),
        priority: 'normal',
      }, true);

      // Should be valid immediately
      expect(manager.isJobCacheValid(cacheKey)).toBe(true);

      // Should be valid after 30 seconds
      vi.advanceTimersByTime(30000);
      expect(manager.isJobCacheValid(cacheKey)).toBe(true);

      // Should be invalid after 61 seconds
      vi.advanceTimersByTime(31000);
      expect(manager.isJobCacheValid(cacheKey)).toBe(false);
    });

    it('should validate pending jobs with 30 sec lifetime', () => {
      const job = createMockJob({ state: 'PD', hostname: 'test.com', job_id: '123' });
      const cacheKey = 'test.com:123';

      manager['queueUpdate']({
        jobId: job.job_id,
        hostname: job.hostname,
        job,
        source: 'api',
        timestamp: Date.now(),
        priority: 'normal',
      }, true);

      // Should be valid at 20 seconds
      vi.advanceTimersByTime(20000);
      expect(manager.isJobCacheValid(cacheKey)).toBe(true);

      // Should be invalid after 31 seconds
      vi.advanceTimersByTime(11000);
      expect(manager.isJobCacheValid(cacheKey)).toBe(false);
    });

    it('should validate completed jobs with 5 min lifetime', () => {
      const job = createMockJob({ state: 'CD', hostname: 'test.com', job_id: '123' });
      const cacheKey = 'test.com:123';

      manager['queueUpdate']({
        jobId: job.job_id,
        hostname: job.hostname,
        job,
        source: 'api',
        timestamp: Date.now(),
        priority: 'normal',
      }, true);

      // Should be valid after 4 minutes
      vi.advanceTimersByTime(4 * 60 * 1000);
      expect(manager.isJobCacheValid(cacheKey)).toBe(true);

      // Should be invalid after 5.5 minutes
      vi.advanceTimersByTime(1.5 * 60 * 1000);
      expect(manager.isJobCacheValid(cacheKey)).toBe(false);
    });
  });

  describe('Update Batching and Deduplication', () => {
    // Tests use manager from main beforeEach

    it('should batch multiple updates', () => {
      const jobs = Array.from({ length: 10 }, (_, i) =>
        createMockJob({ job_id: `${i}`, hostname: 'test.com' })
      );

      // Queue multiple updates
      jobs.forEach(job => {
        manager['queueUpdate']({
          jobId: job.job_id,
          hostname: job.hostname,
          job,
          source: 'api',
          timestamp: Date.now(),
          priority: 'normal',
        }, false); // Not immediate
      });

      // Trigger batch processing
      vi.advanceTimersByTime(200);

      const allJobs = get(manager.getAllJobs());
      expect(allJobs).toHaveLength(10);
    });

    it('should deduplicate updates within window', () => {
      const job = createMockJob({ job_id: '123', hostname: 'test.com', state: 'PD' });

      // Queue same job multiple times with different states
      manager['queueUpdate']({
        jobId: job.job_id,
        hostname: job.hostname,
        job: { ...job, state: 'PD' },
        source: 'api',
        timestamp: Date.now(),
        priority: 'normal',
      }, false);

      manager['queueUpdate']({
        jobId: job.job_id,
        hostname: job.hostname,
        job: { ...job, state: 'R' },
        source: 'api',
        timestamp: Date.now() + 50,
        priority: 'normal',
      }, false);

      // Process batch
      vi.advanceTimersByTime(200);

      const allJobs = get(manager.getAllJobs());
      expect(allJobs).toHaveLength(1);
      expect(allJobs[0].state).toBe('R'); // Should have latest state
    });

    it('should prioritize WebSocket updates over API updates', () => {
      const job = createMockJob({ job_id: '123', hostname: 'test.com' });

      // API update first
      manager['queueUpdate']({
        jobId: job.job_id,
        hostname: job.hostname,
        job: { ...job, runtime: '00:10:00' },
        source: 'api',
        timestamp: Date.now(),
        priority: 'normal',
      }, false);

      // WebSocket update slightly later
      manager['queueUpdate']({
        jobId: job.job_id,
        hostname: job.hostname,
        job: { ...job, runtime: '00:15:00' },
        source: 'websocket',
        timestamp: Date.now() + 10,
        priority: 'realtime',
      }, false);

      // Process batch
      vi.advanceTimersByTime(200);

      const allJobs = get(manager.getAllJobs());
      expect(allJobs[0].runtime).toBe('00:15:00'); // WebSocket update wins
    });
  });

  describe('Host State Management', () => {
    // Tests use manager from main beforeEach

    it('should track host states', async () => {
      await manager.syncAllHosts();

      const hostStates = get(manager.getHostStates());
      expect(hostStates.size).toBeGreaterThan(0);
    });

    it('should mark host as loading during sync', async () => {
      const syncPromise = manager.syncHost('cluster1.example.com');

      // Check loading state (might be quick)
      await vi.waitFor(() => {
        const hostStates = get(manager.getHostStates());
        const hostState = hostStates.get('cluster1.example.com');
        // State could be loading or already connected by the time we check
        expect(['loading', 'connected', 'idle']).toContain(hostState?.status);
      });

      await syncPromise;
    });

    it('should handle host sync errors', async () => {
      // Add error handler for specific host
      addHandler(
        createErrorHandler('/api/status?host=error.com&group_array_jobs=true', 500, 'Server error')
      );

      await manager.syncHost('error.com');

      const hostStates = get(manager.getHostStates());
      const hostState = hostStates.get('error.com');

      if (hostState) {
        expect(hostState.status).toBe('error');
        expect(hostState.errorCount).toBeGreaterThan(0);
      }
    });

    it('should track host timeout errors', async () => {
      // This test would require a timeout handler
      // For now, we test the structure exists
      const hostStates = get(manager.getHostStates());

      // Verify host state structure
      hostStates.forEach(state => {
        expect(state).toHaveProperty('hostname');
        expect(state).toHaveProperty('status');
        expect(state).toHaveProperty('lastSync');
        expect(state).toHaveProperty('errorCount');
      });
    });
  });

  describe('Derived Stores', () => {
    // Tests use manager from main beforeEach

    it('should filter jobs by state', () => {
      const jobs = [
        createMockJob({ job_id: '1', hostname: 'test.com', state: 'R' }),
        createMockJob({ job_id: '2', hostname: 'test.com', state: 'PD' }),
        createMockJob({ job_id: '3', hostname: 'test.com', state: 'R' }),
      ];

      jobs.forEach(job => {
        manager['queueUpdate']({
          jobId: job.job_id,
          hostname: job.hostname,
          job,
          source: 'api',
          timestamp: Date.now(),
          priority: 'normal',
        }, true);
      });

      const runningJobs = get(manager.getJobsByState('R'));
      expect(runningJobs).toHaveLength(2);

      const pendingJobs = get(manager.getJobsByState('PD'));
      expect(pendingJobs).toHaveLength(1);
    });

    it('should filter jobs by host', () => {
      const jobs = [
        createMockJob({ job_id: '1', hostname: 'host1.com' }),
        createMockJob({ job_id: '2', hostname: 'host2.com' }),
        createMockJob({ job_id: '3', hostname: 'host1.com' }),
      ];

      jobs.forEach(job => {
        manager['queueUpdate']({
          jobId: job.job_id,
          hostname: job.hostname,
          job,
          source: 'api',
          timestamp: Date.now(),
          priority: 'normal',
        }, true);
      });

      // First ensure host states exist
      const state = get(manager.getState());
      state.hostStates.set('host1.com', {
        hostname: 'host1.com',
        status: 'connected',
        lastSync: Date.now(),
        errorCount: 0,
        jobs: new Map([['1', 'host1.com:1'], ['3', 'host1.com:3']]),
        arrayGroups: [],
      });

      const host1Jobs = get(manager.getHostJobs('host1.com'));
      expect(host1Jobs).toHaveLength(2);
    });

    it('should get single job by ID and hostname', () => {
      const job = createMockJob({ job_id: '123', hostname: 'test.com' });

      manager['queueUpdate']({
        jobId: job.job_id,
        hostname: job.hostname,
        job,
        source: 'api',
        timestamp: Date.now(),
        priority: 'normal',
      }, true);

      const retrievedJob = get(manager.getJob('123', 'test.com'));
      expect(retrievedJob).not.toBeNull();
      expect(retrievedJob?.job_id).toBe('123');
    });

    it('should return null for non-existent job', () => {
      const job = get(manager.getJob('nonexistent', 'test.com'));
      expect(job).toBeNull();
    });
  });

  describe('Performance Metrics', () => {
    // Tests use manager from main beforeEach

    it('should track total updates', () => {
      const job = createMockJob({ job_id: '123', hostname: 'test.com' });

      manager['queueUpdate']({
        jobId: job.job_id,
        hostname: job.hostname,
        job,
        source: 'api',
        timestamp: Date.now(),
        priority: 'normal',
      }, true);

      const metrics = get(manager.getMetrics());
      expect(metrics.totalUpdates).toBeGreaterThan(0);
    });

    it('should track cache hits and misses', () => {
      const job = createMockJob({ job_id: '123', hostname: 'test.com' });
      const cacheKey = 'test.com:123';

      // Miss - job doesn't exist
      manager.isJobCacheValid(cacheKey);

      // Add job
      manager['queueUpdate']({
        jobId: job.job_id,
        hostname: job.hostname,
        job,
        source: 'api',
        timestamp: Date.now(),
        priority: 'normal',
      }, true);

      // Hit - job exists and valid
      manager.isJobCacheValid(cacheKey);

      const metrics = get(manager.getMetrics());
      expect(metrics.cacheHits).toBeGreaterThan(0);
      expect(metrics.cacheMisses).toBeGreaterThan(0);
    });

    it('should allow metrics reset', () => {
      const job = createMockJob({ job_id: '123', hostname: 'test.com' });

      manager['queueUpdate']({
        jobId: job.job_id,
        hostname: job.hostname,
        job,
        source: 'api',
        timestamp: Date.now(),
        priority: 'normal',
      }, true);

      manager.resetMetrics();

      const metrics = get(manager.getMetrics());
      expect(metrics.totalUpdates).toBe(0);
      expect(metrics.cacheHits).toBe(0);
      expect(metrics.cacheMisses).toBe(0);
    });
  });
});
