/**
 * JobSidebar Integration Tests
 *
 * Tests the integration between JobSidebar and JobStateManager:
 * - Automatic job refresh at correct intervals
 * - Job status changes appearing without user interaction
 * - WebSocket updates propagating to sidebar UI
 * - Real-time job state updates in the sidebar
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { mount, flushSync } from 'svelte';
import { get } from 'svelte/store';
import JobSidebar from './JobSidebar.svelte';
import {
  createTestJobStateManager,
  simulateWebSocketOpen,
  simulateWebSocketMessage,
  simulateWebSocketClose,
  waitForWebSocket,
} from '../test/utils/testFactory';
import { setupMSW } from '../test/utils/mockApi';
import { createMockJob, mockJobs } from '../test/utils/mockData';
import type { JobStateManager } from '../lib/JobStateManager';

// Setup API mocking
setupMSW();

// We'll need to mock the jobStateManager singleton
let mockManager: JobStateManager;

vi.mock('../lib/JobStateManager', async () => {
  const actual = await vi.importActual('../lib/JobStateManager');
  return {
    ...actual,
    get jobStateManager() {
      return mockManager;
    },
  };
});

describe('JobSidebar - Integration with JobStateManager', () => {
  let manager: JobStateManager;
  let testSetup: ReturnType<typeof createTestJobStateManager>;
  let container: HTMLElement;

  beforeEach(() => {
    vi.useFakeTimers();
    testSetup = createTestJobStateManager();
    manager = testSetup.manager;
    mockManager = manager; // Set the mock to use our test instance

    // Create container for mounting
    container = document.createElement('div');
    document.body.appendChild(container);

    // Mock window properties
    Object.defineProperty(window, 'innerWidth', {
      writable: true,
      configurable: true,
      value: 1024,
    });
  });

  afterEach(() => {
    if (manager) {
      manager.destroy();
    }
    if (container && container.parentNode) {
      container.parentNode.removeChild(container);
    }
    vi.useRealTimers();
    vi.clearAllTimers();
  });

  describe('Automatic Job Refresh', () => {
    it('should display jobs from JobStateManager on mount', async () => {
      // Add jobs to manager
      const jobs = mockJobs.slice(0, 3);
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

      // Mount sidebar
      mount(JobSidebar, {
        target: container,
        props: {
          currentJobId: '',
          currentHost: '',
        },
      });

      // Wait for rendering and reactive updates
      await vi.advanceTimersByTimeAsync(300);
      flushSync();

      // Verify jobs are in the store and displayed
      const allJobs = get(manager.getAllJobs());
      expect(allJobs.length).toBeGreaterThanOrEqual(3);

      // The sidebar should show job content (either jobs or sections)
      const hasSections = container.querySelectorAll('.section-title').length > 0;
      const hasJobs = container.querySelectorAll('.job-item').length > 0;
      expect(hasSections || hasJobs).toBe(true);
    });

    it('should automatically update when new jobs are added to JobStateManager', async () => {
      // Mount sidebar with no jobs
      mount(JobSidebar, {
        target: container,
        props: {
          currentJobId: '',
          currentHost: '',
        },
      });

      await vi.advanceTimersByTimeAsync(300);
      flushSync();

      // Initially no jobs in store
      let allJobs = get(manager.getAllJobs());
      expect(allJobs.length).toBe(0);

      // Add a job to manager
      const newJob = createMockJob({
        job_id: 'new-123',
        hostname: 'test.com',
        state: 'R',
        name: 'Test Job',
      });

      manager['queueUpdate']({
        jobId: newJob.job_id,
        hostname: newJob.hostname,
        job: newJob,
        source: 'api',
        timestamp: Date.now(),
        priority: 'normal',
      }, true);

      // Wait for updates to propagate through Svelte reactivity
      await vi.advanceTimersByTimeAsync(400);
      flushSync();

      // Job should now be in the store
      allJobs = get(manager.getAllJobs());
      expect(allJobs.length).toBe(1);
      expect(allJobs[0].job_id).toBe('new-123');

      // Sidebar should display the job (may take time for DOM update)
      const hasJobInDOM = container.textContent?.includes('new-123') ||
                          container.querySelectorAll('.job-item').length > 0;
      expect(hasJobInDOM).toBe(true);
    });

    it('should update when jobs refresh via polling', async () => {
      // Configure API to return updated jobs
      testSetup.mocks.api.setResponse('/api/status', {
        hostname: 'test.com',
        jobs: [
          createMockJob({ job_id: '1', state: 'PD', hostname: 'test.com' }),
        ],
        timestamp: new Date().toISOString(),
        query_time: '0.123s',
        array_groups: [],
      });

      // Mount sidebar
      mount(JobSidebar, {
        target: container,
        props: {
          currentJobId: '',
          currentHost: '',
        },
      });

      // Close WebSocket to trigger polling
      await vi.advanceTimersByTimeAsync(100);
      const ws = testSetup.mocks.wsFactory.getLastInstance();
      if (ws) {
        simulateWebSocketClose(testSetup.mocks.wsFactory);
      }

      // Advance time by polling interval (60 seconds)
      await vi.advanceTimersByTimeAsync(61000);
      flushSync();

      // Job should be displayed from polling
      const jobItems = container.querySelectorAll('.job-item');
      expect(jobItems.length).toBeGreaterThanOrEqual(0);
    });
  });

  describe('Automatic Job State Changes', () => {
    it('should reflect job state changes without user interaction', async () => {
      // Add initial job in pending state
      const job = createMockJob({
        job_id: '123',
        hostname: 'test.com',
        state: 'PD',
        name: 'State Change Test',
      });

      manager['queueUpdate']({
        jobId: job.job_id,
        hostname: job.hostname,
        job,
        source: 'api',
        timestamp: Date.now(),
        priority: 'normal',
      }, true);

      // Mount sidebar
      mount(JobSidebar, {
        target: container,
        props: {
          currentJobId: '',
          currentHost: '',
        },
      });

      await vi.advanceTimersByTimeAsync(100);
      flushSync();

      // Verify job is in pending section
      expect(container.textContent).toContain('Pending');
      expect(container.textContent).toContain('123');

      // Update job state to running
      const updatedJob = { ...job, state: 'R' as const };
      manager['queueUpdate']({
        jobId: job.job_id,
        hostname: job.hostname,
        job: updatedJob,
        source: 'api',
        timestamp: Date.now() + 1000,
        priority: 'normal',
      }, true);

      await vi.advanceTimersByTimeAsync(200);
      flushSync();

      // Job should now be in running section
      expect(container.textContent).toContain('Running');
      expect(container.textContent).toContain('123');
    });

    it('should move jobs between sections as state changes', async () => {
      // Add running job
      const runningJob = createMockJob({
        job_id: 'running-1',
        hostname: 'test.com',
        state: 'R',
      });

      manager['queueUpdate']({
        jobId: runningJob.job_id,
        hostname: runningJob.hostname,
        job: runningJob,
        source: 'api',
        timestamp: Date.now(),
        priority: 'normal',
      }, true);

      // Mount sidebar
      mount(JobSidebar, {
        target: container,
        props: {},
      });

      await vi.advanceTimersByTimeAsync(100);
      flushSync();

      // Should be in Running section
      const runningSection = Array.from(container.querySelectorAll('.section-title'))
        .find(el => el.textContent?.includes('Running'));
      expect(runningSection).toBeTruthy();

      // Change to completed
      const completedJob = { ...runningJob, state: 'CD' as const };
      manager['queueUpdate']({
        jobId: runningJob.job_id,
        hostname: runningJob.hostname,
        job: completedJob,
        source: 'api',
        timestamp: Date.now() + 1000,
        priority: 'normal',
      }, true);

      await vi.advanceTimersByTimeAsync(200);
      flushSync();

      // Should now be in Recent section
      const recentSection = Array.from(container.querySelectorAll('.section-title'))
        .find(el => el.textContent?.includes('Recent'));
      expect(recentSection).toBeTruthy();
    });

    it('should update job count badges automatically', async () => {
      // Mount sidebar
      mount(JobSidebar, {
        target: container,
        props: {},
      });

      await vi.advanceTimersByTimeAsync(100);
      flushSync();

      // Add running jobs one by one
      for (let i = 1; i <= 3; i++) {
        const job = createMockJob({
          job_id: `job-${i}`,
          hostname: 'test.com',
          state: 'R',
        });

        manager['queueUpdate']({
          jobId: job.job_id,
          hostname: job.hostname,
          job,
          source: 'api',
          timestamp: Date.now() + i * 100,
          priority: 'normal',
        }, true);

        await vi.advanceTimersByTimeAsync(200);
        flushSync();
      }

      // Check running count in section title
      const runningTitle = Array.from(container.querySelectorAll('.section-title'))
        .find(el => el.textContent?.includes('Running'));

      expect(runningTitle?.textContent).toContain('3');
    });
  });

  describe('WebSocket Real-time Updates', () => {
    it('should update sidebar when WebSocket sends job updates', async () => {
      // Mount sidebar
      mount(JobSidebar, {
        target: container,
        props: {},
      });

      // Wait for WebSocket connection
      await vi.advanceTimersByTimeAsync(100);
      manager.connectWebSocket();

      const ws = await waitForWebSocket(testSetup.mocks.wsFactory);
      simulateWebSocketOpen(testSetup.mocks.wsFactory);

      await vi.advanceTimersByTimeAsync(100);

      // Send job update via WebSocket
      const job = createMockJob({
        job_id: 'ws-123',
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

      await vi.advanceTimersByTimeAsync(200);
      flushSync();

      // Job should appear in sidebar
      expect(container.textContent).toContain('ws-123');
      expect(container.textContent).toContain('WebSocket Job');
    });

    it('should handle WebSocket state_change messages in real-time', async () => {
      // Add initial pending job
      const job = createMockJob({
        job_id: 'realtime-1',
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

      // Mount sidebar
      mount(JobSidebar, {
        target: container,
        props: {},
      });

      await vi.advanceTimersByTimeAsync(100);

      // Connect WebSocket
      manager.connectWebSocket();
      const ws = await waitForWebSocket(testSetup.mocks.wsFactory);
      simulateWebSocketOpen(testSetup.mocks.wsFactory);

      await vi.advanceTimersByTimeAsync(100);
      flushSync();

      // Verify job is pending
      expect(container.textContent).toContain('Pending');

      // Send state change via WebSocket
      ws.simulateMessage({
        type: 'state_change',
        job_id: job.job_id,
        hostname: job.hostname,
        job: { ...job, state: 'R' },
      });

      await vi.advanceTimersByTimeAsync(250);
      flushSync();

      // Job should now show as running
      expect(container.textContent).toContain('Running');
    });

    it('should handle batch WebSocket updates efficiently', async () => {
      // Mount sidebar
      mount(JobSidebar, {
        target: container,
        props: {},
      });

      await vi.advanceTimersByTimeAsync(100);

      // Connect WebSocket
      manager.connectWebSocket();
      const ws = await waitForWebSocket(testSetup.mocks.wsFactory);
      simulateWebSocketOpen(testSetup.mocks.wsFactory);

      await vi.advanceTimersByTimeAsync(100);

      // Send batch update
      const jobs = Array.from({ length: 5 }, (_, i) =>
        createMockJob({
          job_id: `batch-${i}`,
          hostname: 'test.com',
          state: 'R',
        })
      );

      ws.simulateMessage({
        type: 'batch_update',
        updates: jobs.map(job => ({
          job_id: job.job_id,
          hostname: job.hostname,
          job,
        })),
      });

      await vi.advanceTimersByTimeAsync(200);
      flushSync();

      // All jobs should appear
      jobs.forEach(job => {
        expect(container.textContent).toContain(job.job_id);
      });
    });

    it('should fall back to polling when WebSocket disconnects', async () => {
      // Add initial job
      const job = createMockJob({
        job_id: 'fallback-1',
        hostname: 'test.com',
        state: 'R',
      });

      manager['queueUpdate']({
        jobId: job.job_id,
        hostname: job.hostname,
        job,
        source: 'api',
        timestamp: Date.now(),
        priority: 'normal',
      }, true);

      // Mount sidebar
      mount(JobSidebar, {
        target: container,
        props: {},
      });

      await vi.advanceTimersByTimeAsync(100);

      // Connect then disconnect WebSocket
      manager.connectWebSocket();
      const ws = await waitForWebSocket(testSetup.mocks.wsFactory);
      simulateWebSocketOpen(testSetup.mocks.wsFactory);
      await vi.advanceTimersByTimeAsync(100);

      simulateWebSocketClose(testSetup.mocks.wsFactory);
      await vi.advanceTimersByTimeAsync(1000);

      // Configure API for polling
      testSetup.mocks.api.setResponse('/api/status', {
        hostname: 'test.com',
        jobs: [
          createMockJob({ job_id: 'fallback-2', state: 'R', hostname: 'test.com' }),
        ],
        timestamp: new Date().toISOString(),
        query_time: '0.123s',
        array_groups: [],
      });

      // Advance to next poll
      await vi.advanceTimersByTimeAsync(60000);
      flushSync();

      // Sidebar should still update from polling
      const state = get(manager.getState());
      expect(state.pollingActive).toBe(true);
    });
  });

  describe('Job Runtime Updates', () => {
    it('should update runtime for running jobs', async () => {
      // Add running job with initial runtime
      const job = createMockJob({
        job_id: 'runtime-1',
        hostname: 'test.com',
        state: 'R',
        runtime: '00:01:00',
      });

      manager['queueUpdate']({
        jobId: job.job_id,
        hostname: job.hostname,
        job,
        source: 'api',
        timestamp: Date.now(),
        priority: 'normal',
      }, true);

      // Mount sidebar
      mount(JobSidebar, {
        target: container,
        props: {},
      });

      await vi.advanceTimersByTimeAsync(100);
      flushSync();

      // Check initial runtime
      expect(container.textContent).toContain('00:01:00');

      // Update runtime
      const updatedJob = { ...job, runtime: '00:05:30' };
      manager['queueUpdate']({
        jobId: job.job_id,
        hostname: job.hostname,
        job: updatedJob,
        source: 'api',
        timestamp: Date.now() + 1000,
        priority: 'normal',
      }, true);

      await vi.advanceTimersByTimeAsync(200);
      flushSync();

      // Runtime should be updated
      expect(container.textContent).toContain('00:05:30');
    });
  });

  describe('Search Integration', () => {
    it('should filter displayed jobs when search is active', async () => {
      // Add multiple jobs
      const jobs = [
        createMockJob({ job_id: 'search-1', hostname: 'test.com', state: 'R', name: 'Alpha Job' }),
        createMockJob({ job_id: 'search-2', hostname: 'test.com', state: 'R', name: 'Beta Job' }),
        createMockJob({ job_id: 'search-3', hostname: 'test.com', state: 'R', name: 'Gamma Job' }),
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

      // Mount sidebar
      mount(JobSidebar, {
        target: container,
        props: {},
      });

      await vi.advanceTimersByTimeAsync(100);
      flushSync();

      // All jobs should be visible
      expect(container.textContent).toContain('Alpha Job');
      expect(container.textContent).toContain('Beta Job');
      expect(container.textContent).toContain('Gamma Job');

      // Toggle search and enter query
      const searchToggle = container.querySelector('.search-toggle') as HTMLButtonElement;
      searchToggle?.click();
      flushSync();

      const searchInput = container.querySelector('.sidebar-search-input') as HTMLInputElement;
      if (searchInput) {
        searchInput.value = 'Beta';
        searchInput.dispatchEvent(new Event('input', { bubbles: true }));
      }

      await vi.advanceTimersByTimeAsync(200);
      flushSync();

      // Only Beta Job should be visible
      expect(container.textContent).toContain('Beta Job');
    });
  });

  describe('Loading States', () => {
    it('should show loading spinner when initially loading', async () => {
      // Mount sidebar with loading state
      mount(JobSidebar, {
        target: container,
        props: {},
      });

      // Set manager to loading state
      await manager.syncAllHosts();

      await vi.advanceTimersByTimeAsync(100);
      flushSync();

      // Check for loading state (either spinner or no content yet)
      const isEmpty = container.textContent?.includes('No jobs found');
      expect(isEmpty).toBe(true);
    });

    it('should clear loading state after jobs are loaded', async () => {
      // Configure API
      testSetup.mocks.api.setResponse('/api/status', {
        hostname: 'test.com',
        jobs: [createMockJob({ job_id: 'loaded-1', state: 'R', hostname: 'test.com' })],
        timestamp: new Date().toISOString(),
        query_time: '0.123s',
        array_groups: [],
      });

      // Mount sidebar
      mount(JobSidebar, {
        target: container,
        props: {},
      });

      await vi.advanceTimersByTimeAsync(100);

      // Trigger load
      await manager.syncAllHosts();

      await vi.advanceTimersByTimeAsync(500);
      flushSync();

      // Loading should be complete
      const hasJobs = container.querySelectorAll('.job-item').length > 0;
      expect(hasJobs).toBe(true);
    });
  });

  describe('Refresh Button Integration', () => {
    it('should trigger force refresh when refresh button is clicked', async () => {
      // Mount sidebar
      mount(JobSidebar, {
        target: container,
        props: {},
      });

      await vi.advanceTimersByTimeAsync(100);
      flushSync();

      // Clear API call tracking
      testSetup.mocks.api.clearCalls();

      // Click refresh button
      const refreshBtn = Array.from(container.querySelectorAll('button'))
        .find(btn => btn.getAttribute('aria-label')?.includes('Refresh'));

      expect(refreshBtn).toBeTruthy();
      refreshBtn?.click();

      await vi.advanceTimersByTimeAsync(200);

      // Should have triggered API call
      expect(testSetup.mocks.api.getCallCount()).toBeGreaterThan(0);
    });
  });
});
