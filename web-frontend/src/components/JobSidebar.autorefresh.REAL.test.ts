/**
 * REAL Auto-refresh Tests (No Manual Triggers)
 *
 * These tests verify that polling ACTUALLY happens automatically
 * without manually calling syncAllHosts()
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { get } from 'svelte/store';
import {
  createTestJobStateManager,
  simulateWebSocketClose,
  waitForWebSocket,
} from '../test/utils/testFactory';
import { setupMSW } from '../test/utils/mockApi';
import { createMockJob } from '../test/utils/mockData';
import type { JobStateManager } from '../lib/JobStateManager';

setupMSW();

describe('JobSidebar - REAL Automatic Polling (No Manual Triggers)', () => {
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

  it('should automatically poll and fetch state changes WITHOUT manual syncAllHosts() call', async () => {
    // Initial state: Job is PENDING
    testSetup.mocks.api.setResponse('/api/status', {
      hostname: 'test.com',
      jobs: [
        createMockJob({ job_id: 'auto-poll-test', state: 'PD', hostname: 'test.com' }),
      ],
      timestamp: new Date().toISOString(),
      query_time: '0.123s',
      array_groups: [],
    });

    // Start manager and disable WebSocket to force polling
    manager.connectWebSocket();
    const ws = await waitForWebSocket(testSetup.mocks.wsFactory);
    simulateWebSocketClose(testSetup.mocks.wsFactory);

    await vi.advanceTimersByTimeAsync(1000);

    // Do initial sync to populate job
    await manager.syncAllHosts();
    await vi.advanceTimersByTimeAsync(500);

    // Verify initial state
    let allJobs = get(manager.getAllJobs());
    expect(allJobs.find(j => j.job_id === 'auto-poll-test')?.state).toBe('PD');

    // CHANGE THE SOURCE: Job is now running
    testSetup.mocks.api.setResponse('/api/status', {
      hostname: 'test.com',
      jobs: [
        createMockJob({ job_id: 'auto-poll-test', state: 'R', hostname: 'test.com' }),
      ],
      timestamp: new Date().toISOString(),
      query_time: '0.123s',
      array_groups: [],
    });

    // Clear API call tracking
    testSetup.mocks.api.clearCalls();

    // ⚠️ CRITICAL: DO NOT call syncAllHosts() manually
    // Just advance time and see if polling happens automatically
    await vi.advanceTimersByTimeAsync(65000); // 65 seconds - past poll interval

    // Check if API was called automatically by polling
    const apiCallCount = testSetup.mocks.api.getCallCount();

    // If this fails, polling is NOT working automatically!
    expect(apiCallCount).toBeGreaterThan(0);

    // If polling worked, job state should be updated
    allJobs = get(manager.getAllJobs());
    const job = allJobs.find(j => j.job_id === 'auto-poll-test');

    // This might fail if polling doesn't actually trigger
    expect(job?.state).toBe('R');
  });

  it('should continue automatic polling through multiple state changes', async () => {
    // Start with PENDING
    testSetup.mocks.api.setResponse('/api/status', {
      hostname: 'test.com',
      jobs: [
        createMockJob({ job_id: 'lifecycle-auto', state: 'PD', hostname: 'test.com' }),
      ],
      timestamp: new Date().toISOString(),
      query_time: '0.123s',
      array_groups: [],
    });

    // Disable WebSocket
    manager.connectWebSocket();
    await waitForWebSocket(testSetup.mocks.wsFactory);
    simulateWebSocketClose(testSetup.mocks.wsFactory);
    await vi.advanceTimersByTimeAsync(1000);

    // Initial population
    await manager.syncAllHosts();
    await vi.advanceTimersByTimeAsync(500);

    testSetup.mocks.api.clearCalls();

    // Change 1: PENDING → RUNNING
    testSetup.mocks.api.setResponse('/api/status', {
      hostname: 'test.com',
      jobs: [
        createMockJob({ job_id: 'lifecycle-auto', state: 'R', hostname: 'test.com' }),
      ],
      timestamp: new Date().toISOString(),
      query_time: '0.123s',
      array_groups: [],
    });

    // Wait for first automatic poll
    await vi.advanceTimersByTimeAsync(65000);

    // Should have automatically polled
    expect(testSetup.mocks.api.getCallCount()).toBeGreaterThan(0);

    let allJobs = get(manager.getAllJobs());
    expect(allJobs.find(j => j.job_id === 'lifecycle-auto')?.state).toBe('R');

    testSetup.mocks.api.clearCalls();

    // Change 2: RUNNING → COMPLETED
    testSetup.mocks.api.setResponse('/api/status', {
      hostname: 'test.com',
      jobs: [
        createMockJob({ job_id: 'lifecycle-auto', state: 'CD', hostname: 'test.com' }),
      ],
      timestamp: new Date().toISOString(),
      query_time: '0.123s',
      array_groups: [],
    });

    // Wait for second automatic poll
    await vi.advanceTimersByTimeAsync(65000);

    // Should have polled again automatically
    expect(testSetup.mocks.api.getCallCount()).toBeGreaterThan(0);

    allJobs = get(manager.getAllJobs());
    expect(allJobs.find(j => j.job_id === 'lifecycle-auto')?.state).toBe('CD');
  });
});
