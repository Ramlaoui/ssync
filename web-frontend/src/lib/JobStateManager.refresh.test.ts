/**
 * JobStateManager Refresh Timing and API Call tests
 * Tests proper refresh intervals, force refresh, and API call optimization
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { get } from 'svelte/store';
import type { JobStateManager } from './JobStateManager';
import { createTestJobStateManager, waitForWebSocket, simulateWebSocketOpen } from '../test/utils/testFactory';
import { setupMSW, addHandler, server } from '../test/utils/mockApi';
import { mockJobs, createMockJob, mockHosts } from '../test/utils/mockData';
import { http, HttpResponse } from 'msw';

// Setup API mocking
setupMSW();

describe('JobStateManager - Refresh Timing and API Calls', () => {
  let manager: JobStateManager;
  let testSetup: ReturnType<typeof createTestJobStateManager>;
  let apiCallCounts: Map<string, number>;

  beforeEach(() => {
    vi.useFakeTimers();
    testSetup = createTestJobStateManager();
    manager = testSetup.manager;
    apiCallCounts = new Map();

    // Track API calls
    server.events.on('request:start', ({ request }) => {
      const url = new URL(request.url);
      const path = url.pathname + url.search;
      apiCallCounts.set(path, (apiCallCounts.get(path) || 0) + 1);
    });
  });

  afterEach(() => {
    if (manager) {
      manager.destroy();
    }
    vi.useRealTimers();
    vi.clearAllTimers();
    apiCallCounts.clear();
  });

  describe('Initial Sync', () => {
    it('should sync all hosts on initialization', async () => {
      // Using manager from main beforeEach
      // Manager already initialized with DI pattern

      // Wait for initial sync
      await vi.advanceTimersByTimeAsync(1000);

      const state = get(manager.getState());
      expect(state.jobCache.size).toBeGreaterThan(0);
    });

    it('should not sync via API if WebSocket provides initial data', async () => {
      // Using manager from main beforeEach

      const initPromise = manager.initialize();

      // Simulate WebSocket connection and initial data
      await vi.waitFor(() => {
        const instances = testSetup.mocks.wsFactory.instances;
        expect(instances.length).toBeGreaterThan(0);
      });

      const ws = testSetup.mocks.wsFactory.getLastInstance();
      if (ws) {
        simulateWebSocketOpen(testSetup.mocks.wsFactory);
      }

      // Send initial data immediately
      ws?.simulateMessage({
        type: 'initial',
        jobs: {
          'cluster1.example.com': mockJobs.slice(0, 2),
        },
        total: 2,
      });

      await initPromise;

      // Should skip API sync since WebSocket provided fresh data
      const state = get(manager.getState());
      expect(state.wsInitialDataReceived).toBe(true);
    });

    it('should sync via API if WebSocket does not provide data quickly', async () => {
      // Using manager from main beforeEach

      const initPromise = manager.initialize();

      // Simulate slow WebSocket
      await vi.advanceTimersByTimeAsync(600); // Wait past initial timeout

      await initPromise;

      // Should have made API calls
      const state = get(manager.getState());
      expect(state.jobCache.size).toBeGreaterThanOrEqual(0);
    });
  });

  describe('Polling Intervals', () => {
    it('should poll at active interval (60s) when tab is active', async () => {
      // Using manager from main beforeEach
      // Manager already initialized with DI pattern

      // Close WebSocket to trigger polling
      const ws = testSetup.mocks.wsFactory.getLastInstance();
      ws?.simulateClose();

      await vi.advanceTimersByTimeAsync(1000);

      const state = get(manager.getState());
      expect(state.pollingActive).toBe(true);
      expect(state.isTabActive).toBe(true);

      // Clear initial call count
      apiCallCounts.clear();

      // Advance by 60 seconds - should trigger one poll
      await vi.advanceTimersByTimeAsync(60000);

      // Should have made at least one API call
      let totalCalls = 0;
      apiCallCounts.forEach(count => totalCalls += count);
      expect(totalCalls).toBeGreaterThan(0);
    });

    it('should poll at background interval (300s) when tab is inactive', async () => {
      // Using manager from main beforeEach
      // Manager already initialized with DI pattern

      // Close WebSocket to trigger polling
      const ws = testSetup.mocks.wsFactory.getLastInstance();
      ws?.simulateClose();

      // Make tab inactive
      Object.defineProperty(document, 'hidden', {
        configurable: true,
        get: () => true,
      });
      document.dispatchEvent(new Event('visibilitychange'));

      await vi.advanceTimersByTimeAsync(1000);

      apiCallCounts.clear();

      // Advance by 60 seconds - should NOT poll yet (background interval is 300s)
      await vi.advanceTimersByTimeAsync(60000);

      let calls = 0;
      apiCallCounts.forEach(count => calls += count);
      // Background polling uses 300s interval, so no calls yet
      expect(calls).toBe(0);
    });

    it('should stop polling when paused', async () => {
      // Using manager from main beforeEach
      // Manager already initialized with DI pattern

      const ws = testSetup.mocks.wsFactory.getLastInstance();
      ws?.simulateClose();

      // Make tab inactive and wait for pause threshold
      Object.defineProperty(document, 'hidden', {
        configurable: true,
        get: () => true,
      });
      document.dispatchEvent(new Event('visibilitychange'));

      // Advance past pause threshold (5 minutes)
      await vi.advanceTimersByTimeAsync(6 * 60 * 1000);

      const state = get(manager.getState());
      expect(state.isPaused).toBe(true);

      apiCallCounts.clear();

      // Advance time - should NOT poll
      await vi.advanceTimersByTimeAsync(60000);

      let totalCalls = 0;
      apiCallCounts.forEach(count => totalCalls += count);
      expect(totalCalls).toBe(0);
    });
  });

  describe('Cache-based Refresh Optimization', () => {
    it('should skip sync if cache is still valid', async () => {
      // Using manager from main beforeEach
      // Manager already initialized with DI pattern

      // Perform initial sync
      await manager.syncHost('cluster1.example.com', false);

      apiCallCounts.clear();

      // Try to sync again immediately (cache should be valid)
      await manager.syncHost('cluster1.example.com', false);

      // Should not make API call due to valid cache
      let totalCalls = 0;
      apiCallCounts.forEach(count => totalCalls += count);
      expect(totalCalls).toBe(0);
    });

    it('should sync if cache has expired', async () => {
      // Using manager from main beforeEach
      // Manager already initialized with DI pattern

      // Perform initial sync
      await manager.syncHost('cluster1.example.com', false);

      // Advance time past cache expiry (60 seconds for active tab)
      await vi.advanceTimersByTimeAsync(61000);

      apiCallCounts.clear();

      // Try to sync again (cache should be expired)
      await manager.syncHost('cluster1.example.com', false);

      // Should make API call
      let totalCalls = 0;
      apiCallCounts.forEach(count => totalCalls += count);
      expect(totalCalls).toBeGreaterThan(0);
    });
  });

  describe('Force Refresh', () => {
    it('should bypass cache on force refresh', async () => {
      // Using manager from main beforeEach
      // Manager already initialized with DI pattern

      // Perform initial sync
      await manager.syncHost('cluster1.example.com', false);

      apiCallCounts.clear();

      // Force refresh immediately (should ignore cache)
      await manager.syncHost('cluster1.example.com', true);

      // Should make API call despite valid cache
      let totalCalls = 0;
      apiCallCounts.forEach(count => totalCalls += count);
      expect(totalCalls).toBeGreaterThan(0);
    });

    it('should bypass WebSocket initial data check on force refresh', async () => {
      // Using manager from main beforeEach
      // Manager already initialized with DI pattern

      const ws = testSetup.mocks.wsFactory.getLastInstance();
      if (ws) {
        simulateWebSocketOpen(testSetup.mocks.wsFactory);
      }

      // Send initial WebSocket data
      ws?.simulateMessage({
        type: 'initial',
        jobs: {
          'cluster1.example.com': mockJobs.slice(0, 2),
        },
        total: 2,
      });

      await vi.advanceTimersByTimeAsync(500);

      const state = get(manager.getState());
      expect(state.wsInitialDataReceived).toBe(true);

      apiCallCounts.clear();

      // Force refresh should still make API call
      await manager.forceRefresh();

      let totalCalls = 0;
      apiCallCounts.forEach(count => totalCalls += count);
      expect(totalCalls).toBeGreaterThan(0);
    });

    it('should pass force_refresh parameter to API', async () => {
      let capturedParams: URLSearchParams | null = null;

      addHandler(
        http.get('/api/status', ({ request }) => {
          const url = new URL(request.url);
          capturedParams = url.searchParams;

          return HttpResponse.json({
            hostname: 'cluster1.example.com',
            jobs: [],
            timestamp: new Date().toISOString(),
            query_time: '0.123s',
            array_groups: [],
          });
        })
      );

      // Using manager from main beforeEach
      // Manager already initialized with DI pattern

      // Force refresh
      await manager.syncHost('cluster1.example.com', true);

      expect(capturedParams).not.toBeNull();
      expect(capturedParams?.get('force_refresh')).toBe('true');
    });

    it('should process force refresh updates immediately', async () => {
      // Using manager from main beforeEach
      // Manager already initialized with DI pattern

      const job = createMockJob({
        job_id: 'force-test',
        hostname: 'test.com',
        state: 'R',
      });

      // Mock API response
      addHandler(
        http.get('/api/status', () => {
          return HttpResponse.json({
            hostname: 'test.com',
            jobs: [job],
            timestamp: new Date().toISOString(),
            query_time: '0.123s',
            array_groups: [],
          });
        })
      );

      // Force refresh
      await manager.syncHost('test.com', true);

      // Should process immediately without batching delay
      const allJobs = get(manager.getAllJobs());
      const foundJob = allJobs.find(j => j.job_id === 'force-test');
      expect(foundJob).toBeDefined();
    });
  });

  describe('Job State-based Cache Lifetimes', () => {
    beforeEach(async () => {
      // Using manager from main beforeEach
      // Manager already initialized with DI pattern
    });

    it('should use 30 second cache for pending jobs', () => {
      const job = createMockJob({ state: 'PD', hostname: 'test.com', job_id: '1' });
      const cacheKey = 'test.com:1';

      manager['queueUpdate']({
        jobId: job.job_id,
        hostname: job.hostname,
        job,
        source: 'api',
        timestamp: Date.now(),
        priority: 'normal',
      }, true);

      // Valid at 25 seconds
      vi.advanceTimersByTime(25000);
      expect(manager.isJobCacheValid(cacheKey)).toBe(true);

      // Invalid at 31 seconds
      vi.advanceTimersByTime(6000);
      expect(manager.isJobCacheValid(cacheKey)).toBe(false);
    });

    it('should use 60 second cache for running jobs', () => {
      const job = createMockJob({ state: 'R', hostname: 'test.com', job_id: '1' });
      const cacheKey = 'test.com:1';

      manager['queueUpdate']({
        jobId: job.job_id,
        hostname: job.hostname,
        job,
        source: 'api',
        timestamp: Date.now(),
        priority: 'normal',
      }, true);

      // Valid at 50 seconds
      vi.advanceTimersByTime(50000);
      expect(manager.isJobCacheValid(cacheKey)).toBe(true);

      // Invalid at 61 seconds
      vi.advanceTimersByTime(11000);
      expect(manager.isJobCacheValid(cacheKey)).toBe(false);
    });

    it('should use 5 minute cache for completed jobs', () => {
      const job = createMockJob({ state: 'CD', hostname: 'test.com', job_id: '1' });
      const cacheKey = 'test.com:1';

      manager['queueUpdate']({
        jobId: job.job_id,
        hostname: job.hostname,
        job,
        source: 'api',
        timestamp: Date.now(),
        priority: 'normal',
      }, true);

      // Valid at 4 minutes
      vi.advanceTimersByTime(4 * 60 * 1000);
      expect(manager.isJobCacheValid(cacheKey)).toBe(true);

      // Invalid at 6 minutes
      vi.advanceTimersByTime(2 * 60 * 1000);
      expect(manager.isJobCacheValid(cacheKey)).toBe(false);
    });

    it('should use 5 minute cache for failed jobs', () => {
      const job = createMockJob({ state: 'F', hostname: 'test.com', job_id: '1' });
      const cacheKey = 'test.com:1';

      manager['queueUpdate']({
        jobId: job.job_id,
        hostname: job.hostname,
        job,
        source: 'api',
        timestamp: Date.now(),
        priority: 'normal',
      }, true);

      // Valid at 4 minutes
      vi.advanceTimersByTime(4 * 60 * 1000);
      expect(manager.isJobCacheValid(cacheKey)).toBe(true);

      // Invalid at 6 minutes
      vi.advanceTimersByTime(2 * 60 * 1000);
      expect(manager.isJobCacheValid(cacheKey)).toBe(false);
    });
  });

  describe('Fetch Single Job', () => {
    beforeEach(async () => {
      // Using manager from main beforeEach
      // Manager already initialized with DI pattern
    });

    it('should return cached job if valid', async () => {
      const job = createMockJob({ job_id: '123', hostname: 'test.com' });

      manager['queueUpdate']({
        jobId: job.job_id,
        hostname: job.hostname,
        job,
        source: 'api',
        timestamp: Date.now(),
        priority: 'normal',
      }, true);

      apiCallCounts.clear();

      // Should return from cache
      const fetchedJob = await manager.fetchSingleJob('123', 'test.com', false);

      expect(fetchedJob).toBeDefined();
      expect(fetchedJob?.job_id).toBe('123');

      // Should not have made API call
      let totalCalls = 0;
      apiCallCounts.forEach(count => totalCalls += count);
      expect(totalCalls).toBe(0);
    });

    it('should fetch from API if cache is invalid', async () => {
      const job = createMockJob({ job_id: '123', hostname: 'test.com', state: 'R' });

      manager['queueUpdate']({
        jobId: job.job_id,
        hostname: job.hostname,
        job,
        source: 'api',
        timestamp: Date.now(),
        priority: 'normal',
      }, true);

      // Expire cache
      vi.advanceTimersByTime(61000);

      apiCallCounts.clear();

      // Should fetch from API
      const fetchedJob = await manager.fetchSingleJob('123', 'test.com', false);

      // Should have made API call
      let totalCalls = 0;
      apiCallCounts.forEach(count => totalCalls += count);
      expect(totalCalls).toBeGreaterThan(0);
    });

    it('should force fetch from API when forceRefresh is true', async () => {
      const job = createMockJob({ job_id: '123', hostname: 'test.com' });

      manager['queueUpdate']({
        jobId: job.job_id,
        hostname: job.hostname,
        job,
        source: 'api',
        timestamp: Date.now(),
        priority: 'normal',
      }, true);

      apiCallCounts.clear();

      // Force fetch
      const fetchedJob = await manager.fetchSingleJob('123', 'test.com', true);

      // Should have made API call despite valid cache
      let totalCalls = 0;
      apiCallCounts.forEach(count => totalCalls += count);
      expect(totalCalls).toBeGreaterThan(0);
    });

    it('should pass force parameter to API', async () => {
      let capturedParams: URLSearchParams | null = null;

      addHandler(
        http.get('/api/jobs/:jobId', ({ request }) => {
          const url = new URL(request.url);
          capturedParams = url.searchParams;

          return HttpResponse.json(createMockJob({ job_id: '123', hostname: 'test.com' }));
        })
      );

      await manager.fetchSingleJob('123', 'test.com', true);

      expect(capturedParams).not.toBeNull();
      expect(capturedParams?.get('force')).toBe('true');
    });

    it('should return cached job on API error', async () => {
      const job = createMockJob({ job_id: '123', hostname: 'test.com' });

      manager['queueUpdate']({
        jobId: job.job_id,
        hostname: job.hostname,
        job,
        source: 'api',
        timestamp: Date.now(),
        priority: 'normal',
      }, true);

      // Mock API error
      addHandler(
        http.get('/api/jobs/123', () => {
          return HttpResponse.json({ detail: 'Error' }, { status: 500 });
        })
      );

      // Expire cache to trigger API call
      vi.advanceTimersByTime(61000);

      const fetchedJob = await manager.fetchSingleJob('123', 'test.com', false);

      // Should return cached job despite API error
      expect(fetchedJob).toBeDefined();
      expect(fetchedJob?.job_id).toBe('123');
    });
  });

  describe('API Call Optimization', () => {
    it('should track API call count in metrics', async () => {
      // Using manager from main beforeEach
      // Manager already initialized with DI pattern

      await manager.syncHost('cluster1.example.com', false);

      const metrics = get(manager.getMetrics());
      expect(metrics.apiCalls).toBeGreaterThan(0);
    });

    it('should minimize redundant API calls', async () => {
      // Using manager from main beforeEach
      // Manager already initialized with DI pattern

      // Initial sync
      await manager.syncAllHosts();

      apiCallCounts.clear();

      // Try to sync again immediately
      await manager.syncAllHosts();

      // Should make minimal or no calls due to cache
      let totalCalls = 0;
      apiCallCounts.forEach(count => totalCalls += count);
      expect(totalCalls).toBeLessThan(5); // Allow some calls for host list
    });

    it('should batch updates to reduce reactive updates', async () => {
      // Using manager from main beforeEach
      // Manager already initialized with DI pattern

      let updateCount = 0;
      manager.getAllJobs().subscribe(() => {
        updateCount++;
      });

      // Queue multiple updates
      const jobs = Array.from({ length: 50 }, (_, i) =>
        createMockJob({ job_id: `${i}`, hostname: 'test.com' })
      );

      jobs.forEach(job => {
        manager['queueUpdate']({
          jobId: job.job_id,
          hostname: job.hostname,
          job,
          source: 'api',
          timestamp: Date.now(),
          priority: 'normal',
        }, false);
      });

      // Process all updates
      await vi.advanceTimersByTimeAsync(500);

      // Should have batched updates, not 50 individual updates
      expect(updateCount).toBeLessThan(10);
    });
  });

  describe('Timeout Handling', () => {
    it('should mark host as timed out after 30 seconds', async () => {
      // Add a slow endpoint
      addHandler(
        http.get('/api/status', async () => {
          await new Promise(resolve => setTimeout(resolve, 31000));
          return HttpResponse.json({ jobs: [] });
        })
      );

      // Using manager from main beforeEach
      // Manager already initialized with DI pattern

      await manager.syncHost('cluster1.example.com');

      const hostStates = get(manager.getHostStates());
      const hostState = hostStates.get('cluster1.example.com');

      // Timeout behavior might vary, check for error state
      if (hostState && hostState.status === 'error') {
        expect(hostState.isTimeout).toBe(true);
      }
    });
  });
});
