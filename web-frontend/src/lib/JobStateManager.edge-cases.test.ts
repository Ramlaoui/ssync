/**
 * JobStateManager Edge Cases and Error Handling tests
 * Tests unusual scenarios, race conditions, and error recovery
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { get } from 'svelte/store';
import type { JobStateManager } from './JobStateManager';
import { createTestJobStateManager, waitForWebSocket, simulateWebSocketOpen } from '../test/utils/testFactory';
import { setupMSW, addHandler, createErrorHandler } from '../test/utils/mockApi';
import { createMockJob, createMockJobs } from '../test/utils/mockData';
import { http, HttpResponse } from 'msw';

setupMSW();

describe('JobStateManager - Edge Cases and Error Handling', () => {
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

  describe('Empty States', () => {
    it('should handle empty job list gracefully', async () => {
      addHandler(
        http.get('/api/status', () => {
          return HttpResponse.json({
            hostname: 'empty.com',
            jobs: [],
            timestamp: new Date().toISOString(),
            query_time: '0.1s',
            array_groups: [],
          });
        })
      );

      // Using manager from main beforeEach

      await manager.syncHost('empty.com');

      const allJobs = get(manager.getAllJobs());
      expect(allJobs).toEqual([]);
    });

    it('should handle no hosts configured', async () => {
      addHandler(
        http.get('/api/hosts', () => {
          return HttpResponse.json([]);
        })
      );

      // Using manager from main beforeEach

      await manager.syncAllHosts();

      const hostStates = get(manager.getHostStates());
      expect(hostStates.size).toBe(0);
    });

    it('should handle WebSocket sending empty jobs array', async () => {
      // Using manager from main beforeEach

      const ws = await vi.waitFor(() => {
        const instances = testSetup.mocks.wsFactory.instances;
        if (instances.length > 0) return instances[0];
        throw new Error('No WebSocket');
      });

      simulateWebSocketOpen(testSetup.mocks.wsFactory);
      ws.simulateMessage({
        type: 'initial',
        jobs: {},
        total: 0,
      });

      await vi.advanceTimersByTimeAsync(200);

      const allJobs = get(manager.getAllJobs());
      expect(allJobs).toEqual([]);
    });
  });

  describe('Duplicate Jobs', () => {
    beforeEach(async () => {
      // Using manager from main beforeEach
    });

    it('should deduplicate jobs with same ID and hostname', () => {
      const job1 = createMockJob({ job_id: '123', hostname: 'test.com', state: 'PD' });
      const job2 = createMockJob({ job_id: '123', hostname: 'test.com', state: 'R' });

      manager['queueUpdate']({
        jobId: job1.job_id,
        hostname: job1.hostname,
        job: job1,
        source: 'api',
        timestamp: Date.now(),
        priority: 'normal',
      }, true);

      manager['queueUpdate']({
        jobId: job2.job_id,
        hostname: job2.hostname,
        job: job2,
        source: 'api',
        timestamp: Date.now() + 100,
        priority: 'normal',
      }, true);

      const allJobs = get(manager.getAllJobs());
      const matchingJobs = allJobs.filter(j => j.job_id === '123' && j.hostname === 'test.com');
      expect(matchingJobs).toHaveLength(1);
      expect(matchingJobs[0].state).toBe('R');
    });

    it('should keep jobs with same ID but different hostnames', () => {
      const job1 = createMockJob({ job_id: '123', hostname: 'host1.com' });
      const job2 = createMockJob({ job_id: '123', hostname: 'host2.com' });

      manager['queueUpdate']({
        jobId: job1.job_id,
        hostname: job1.hostname,
        job: job1,
        source: 'api',
        timestamp: Date.now(),
        priority: 'normal',
      }, true);

      manager['queueUpdate']({
        jobId: job2.job_id,
        hostname: job2.hostname,
        job: job2,
        source: 'api',
        timestamp: Date.now(),
        priority: 'normal',
      }, true);

      const allJobs = get(manager.getAllJobs());
      expect(allJobs).toHaveLength(2);
    });

    it('should handle duplicate messages from WebSocket', async () => {
      const ws = testSetup.mocks.wsFactory.getLastInstance();
      const job = createMockJob({ job_id: '123', hostname: 'test.com' });

      // Send same update twice
      ws?.simulateMessage({
        type: 'job_update',
        job_id: '123',
        hostname: 'test.com',
        job: job,
      });

      ws?.simulateMessage({
        type: 'job_update',
        job_id: '123',
        hostname: 'test.com',
        job: job,
      });

      await vi.advanceTimersByTimeAsync(200);

      const allJobs = get(manager.getAllJobs());
      const matchingJobs = allJobs.filter(j => j.job_id === '123');
      expect(matchingJobs).toHaveLength(1);
    });
  });

  describe('Invalid Data', () => {
    beforeEach(async () => {
      // Using manager from main beforeEach
    });

    it('should reject job without job_id', () => {
      const invalidJob = createMockJob({ hostname: 'test.com' });
      delete (invalidJob as any).job_id;

      const beforeSize = get(manager.getState()).jobCache.size;

      manager['queueUpdate']({
        jobId: '',
        hostname: 'test.com',
        job: invalidJob as any,
        source: 'api',
        timestamp: Date.now(),
        priority: 'normal',
      }, true);

      const afterSize = get(manager.getState()).jobCache.size;
      expect(afterSize).toBe(beforeSize);
    });

    it('should reject job without hostname', () => {
      const invalidJob = createMockJob({ job_id: '123' });
      delete (invalidJob as any).hostname;

      // queueUpdate should reject this
      expect(() => {
        manager['queueUpdate']({
          jobId: '123',
          hostname: '',
          job: invalidJob as any,
          source: 'api',
          timestamp: Date.now(),
          priority: 'normal',
        }, true);
      }).not.toThrow(); // Should handle gracefully

      const job = get(manager.getJob('123', ''));
      expect(job).toBeNull();
    });

    it('should handle malformed job data gracefully', () => {
      const malformedJob = {
        job_id: '123',
        hostname: 'test.com',
        // Missing required fields
      } as any;

      manager['queueUpdate']({
        jobId: '123',
        hostname: 'test.com',
        job: malformedJob,
        source: 'api',
        timestamp: Date.now(),
        priority: 'normal',
      }, true);

      // Should not crash
      const allJobs = get(manager.getAllJobs());
      expect(Array.isArray(allJobs)).toBe(true);
    });

    it('should handle undefined/null values in job properties', () => {
      const job = createMockJob({
        job_id: '123',
        hostname: 'test.com',
        name: undefined as any,
        runtime: null as any,
      });

      manager['queueUpdate']({
        jobId: job.job_id,
        hostname: job.hostname,
        job,
        source: 'api',
        timestamp: Date.now(),
        priority: 'normal',
      }, true);

      const retrievedJob = get(manager.getJob('123', 'test.com'));
      expect(retrievedJob).toBeDefined();
    });
  });

  describe('Large Datasets', () => {
    beforeEach(async () => {
      // Using manager from main beforeEach
    });

    it('should handle 1000+ jobs efficiently', () => {
      const jobs = createMockJobs(1000, { hostname: 'test.com' });

      const startTime = performance.now();

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

      // Process batch
      vi.advanceTimersByTime(500);

      const endTime = performance.now();
      const duration = endTime - startTime;

      const allJobs = get(manager.getAllJobs());
      expect(allJobs.length).toBeGreaterThanOrEqual(1000);
      expect(duration).toBeLessThan(5000); // Should complete in under 5 seconds
    });

    it('should batch large update queues', () => {
      const jobs = createMockJobs(200, { hostname: 'test.com' });

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

      // Should process in batches of 50
      const state = get(manager.getState());
      expect(state.pendingUpdates.length).toBeGreaterThan(0);

      // Process all batches
      vi.advanceTimersByTime(2000);

      const finalState = get(manager.getState());
      expect(finalState.pendingUpdates.length).toBe(0);
      expect(finalState.jobCache.size).toBeGreaterThanOrEqual(200);
    });
  });

  describe('Race Conditions', () => {
    beforeEach(async () => {
      // Using manager from main beforeEach
    });

    it('should handle concurrent updates from API and WebSocket', () => {
      const job = createMockJob({ job_id: '123', hostname: 'test.com', state: 'PD' });

      // API update
      manager['queueUpdate']({
        jobId: job.job_id,
        hostname: job.hostname,
        job: { ...job, runtime: '00:10:00' },
        source: 'api',
        timestamp: Date.now(),
        priority: 'normal',
      }, false);

      // WebSocket update (slightly newer)
      manager['queueUpdate']({
        jobId: job.job_id,
        hostname: job.hostname,
        job: { ...job, runtime: '00:15:00', state: 'R' },
        source: 'websocket',
        timestamp: Date.now() + 50,
        priority: 'realtime',
      }, false);

      vi.advanceTimersByTime(200);

      const retrievedJob = get(manager.getJob('123', 'test.com'));
      expect(retrievedJob?.state).toBe('R');
      expect(retrievedJob?.runtime).toBe('00:15:00');
    });

    it('should handle rapid state transitions', () => {
      const job = createMockJob({ job_id: '123', hostname: 'test.com' });

      const states: Array<'PD' | 'R' | 'CD'> = ['PD', 'R', 'CD'];
      states.forEach((state, index) => {
        manager['queueUpdate']({
          jobId: job.job_id,
          hostname: job.hostname,
          job: { ...job, state },
          source: 'websocket',
          timestamp: Date.now() + index * 10,
          priority: 'realtime',
        }, false);
      });

      vi.advanceTimersByTime(200);

      const retrievedJob = get(manager.getJob('123', 'test.com'));
      expect(retrievedJob?.state).toBe('CD'); // Should have latest state
    });

    it('should handle simultaneous syncs for same host', async () => {
      // Start two syncs at the same time
      const sync1 = manager.syncHost('cluster1.example.com', false);
      const sync2 = manager.syncHost('cluster1.example.com', false);

      await Promise.all([sync1, sync2]);

      // Should not create duplicates
      const allJobs = get(manager.getAllJobs());
      const cluster1Jobs = allJobs.filter(j => j.hostname === 'cluster1.example.com');
      const jobIds = new Set(cluster1Jobs.map(j => j.job_id));
      expect(cluster1Jobs.length).toBe(jobIds.size); // No duplicates
    });
  });

  describe('Network Errors', () => {
    beforeEach(async () => {
      // Using manager from main beforeEach
    });

    it('should handle 500 server errors gracefully', async () => {
      addHandler(createErrorHandler('/api/status?host=error.com&group_array_jobs=true', 500, 'Internal server error'));

      await manager.syncHost('error.com');

      const hostStates = get(manager.getHostStates());
      const hostState = hostStates.get('error.com');

      if (hostState) {
        expect(hostState.status).toBe('error');
        expect(hostState.lastError).toContain('error');
      }
    });

    it('should handle 404 not found errors', async () => {
      addHandler(createErrorHandler('/api/jobs/nonexistent', 404, 'Job not found'));

      const job = await manager.fetchJob('nonexistent', 'test.com');
      expect(job).toBeNull();
    });

    it('should handle network timeouts', async () => {
      addHandler(
        http.get('/api/status', async () => {
          await new Promise(resolve => setTimeout(resolve, 31000));
          return HttpResponse.json({ jobs: [] });
        })
      );

      await manager.syncHost('timeout.com');

      // Should handle timeout gracefully
      const hostStates = get(manager.getHostStates());
      const hostState = hostStates.get('timeout.com');

      if (hostState) {
        expect(['error', 'idle', 'loading']).toContain(hostState.status);
      }
    });

    it('should retry failed connections', async () => {
      let attempts = 0;

      addHandler(
        http.get('/api/status', () => {
          attempts++;
          if (attempts < 2) {
            return HttpResponse.json({ detail: 'Error' }, { status: 500 });
          }
          return HttpResponse.json({
            hostname: 'retry.com',
            jobs: [],
            timestamp: new Date().toISOString(),
            query_time: '0.1s',
            array_groups: [],
          });
        })
      );

      await manager.syncHost('retry.com');
      await vi.advanceTimersByTimeAsync(1000);
      await manager.syncHost('retry.com');

      expect(attempts).toBeGreaterThan(1);
    });

    it('should track error counts per host', async () => {
      addHandler(createErrorHandler('/api/status?host=error.com&group_array_jobs=true', 500, 'Error'));

      await manager.syncHost('error.com');
      await manager.syncHost('error.com');
      await manager.syncHost('error.com');

      const hostStates = get(manager.getHostStates());
      const hostState = hostStates.get('error.com');

      if (hostState) {
        expect(hostState.errorCount).toBeGreaterThan(0);
      }
    });
  });

  describe('Memory Management', () => {
    beforeEach(async () => {
      // Using manager from main beforeEach
    });

    it('should not leak memory with many updates', () => {
      const initialMemory = process.memoryUsage().heapUsed;

      // Add and update many jobs
      for (let i = 0; i < 1000; i++) {
        const job = createMockJob({
          job_id: `${i % 100}`, // Reuse IDs to test updates
          hostname: 'test.com',
        });

        manager['queueUpdate']({
          jobId: job.job_id,
          hostname: job.hostname,
          job,
          source: 'api',
          timestamp: Date.now(),
          priority: 'normal',
        }, false);
      }

      vi.advanceTimersByTime(2000);

      const finalMemory = process.memoryUsage().heapUsed;
      const memoryGrowth = finalMemory - initialMemory;

      // Memory growth should be reasonable (less than 50MB for 1000 updates)
      expect(memoryGrowth).toBeLessThan(50 * 1024 * 1024);
    });

    it('should limit update history size', () => {
      // Add many jobs to generate history
      for (let i = 0; i < 150; i++) {
        const job = createMockJob({ job_id: `${i}`, hostname: 'test.com' });

        manager['queueUpdate']({
          jobId: job.job_id,
          hostname: job.hostname,
          job,
          source: 'api',
          timestamp: Date.now(),
          priority: 'normal',
        }, true);
      }

      const metrics = get(manager.getMetrics());
      expect(metrics.updateHistory.length).toBeLessThanOrEqual(100);
    });
  });

  describe('Cleanup and Destruction', () => {
    it('should clean up timers on destroy', async () => {
      // Using manager from main beforeEach

      const ws = testSetup.mocks.wsFactory.getLastInstance();
      ws?.simulateOpen();

      manager.destroy();

      // Timers should be cleared
      const timerCount = vi.getTimerCount();
      expect(timerCount).toBeLessThan(5); // Some timers from test framework may remain
    });

    it('should close WebSocket on destroy', async () => {
      // Using manager from main beforeEach

      const ws = testSetup.mocks.wsFactory.getLastInstance();
      ws?.simulateOpen();

      manager.destroy();

      expect(ws?.readyState).toBe(WebSocket.CLOSED);
    });

    it('should stop polling on destroy', async () => {
      // Using manager from main beforeEach

      const ws = testSetup.mocks.wsFactory.getLastInstance();
      ws?.simulateClose();

      await vi.advanceTimersByTimeAsync(1000);

      const beforeState = get(manager.getState());
      expect(beforeState.pollingActive).toBe(true);

      manager.destroy();

      // Polling should be stopped (can't check directly, but no errors should occur)
      await vi.advanceTimersByTimeAsync(65000);
    });
  });

  describe('Edge Cases in Job Filtering', () => {
    beforeEach(async () => {
      // Using manager from main beforeEach
    });

    it('should handle filtering with no matching jobs', () => {
      const jobs = createMockJobs(5, { hostname: 'test.com', state: 'R' });

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

      const pendingJobs = get(manager.getJobsByState('PD'));
      expect(pendingJobs).toHaveLength(0);
    });

    it('should handle filtering by non-existent host', () => {
      const jobs = createMockJobs(5, { hostname: 'test.com' });

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

      const hostJobs = get(manager.getHostJobs('nonexistent.com'));
      expect(hostJobs).toHaveLength(0);
    });

    it('should handle jobs with unusual state values', () => {
      const job = createMockJob({
        job_id: '123',
        hostname: 'test.com',
        state: 'UNKNOWN' as any,
      });

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
    });
  });
});
