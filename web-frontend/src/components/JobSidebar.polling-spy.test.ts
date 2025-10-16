/**
 * Polling Spy Tests - Verify setInterval is called and executes
 *
 * Tests that polling timer is actually set up and fires
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

describe('Polling - Verify setInterval Behavior', () => {
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

  it('should create a setInterval timer when WebSocket closes', async () => {
    // Spy on setInterval
    const setIntervalSpy = vi.spyOn(global, 'setInterval');

    // Connect and close WebSocket to trigger polling
    manager.connectWebSocket();
    const ws = await waitForWebSocket(testSetup.mocks.wsFactory);

    // Clear spy before the action we want to test
    setIntervalSpy.mockClear();

    simulateWebSocketClose(testSetup.mocks.wsFactory);
    await vi.advanceTimersByTimeAsync(1000);

    // Verify setInterval was called to set up polling
    expect(setIntervalSpy).toHaveBeenCalled();

    // Check it was called with correct interval (60000ms = 60s for active tab)
    const calls = setIntervalSpy.mock.calls;
    const pollingCall = calls.find(call => call[1] === 60000);
    expect(pollingCall).toBeDefined();

    setIntervalSpy.mockRestore();
  });

  it('should execute the polling callback when timer fires', async () => {
    // Setup API response
    testSetup.mocks.api.setResponse('/api/status', {
      hostname: 'test.com',
      jobs: [
        createMockJob({ job_id: 'callback-test', state: 'PD', hostname: 'test.com' }),
      ],
      timestamp: new Date().toISOString(),
      query_time: '0.123s',
      array_groups: [],
    });

    // Spy on syncAllHosts method
    const syncSpy = vi.spyOn(manager, 'syncAllHosts');

    // Trigger polling
    manager.connectWebSocket();
    const ws = await waitForWebSocket(testSetup.mocks.wsFactory);
    simulateWebSocketClose(testSetup.mocks.wsFactory);
    await vi.advanceTimersByTimeAsync(1000);

    // Clear the spy (it might have been called during setup)
    syncSpy.mockClear();

    // Advance time to trigger polling interval
    await vi.advanceTimersByTimeAsync(60000);

    // Check if syncAllHosts was called by the polling timer
    expect(syncSpy).toHaveBeenCalled();

    syncSpy.mockRestore();
  });

  it('should verify polling callback executes multiple times', async () => {
    // Setup API
    testSetup.mocks.api.setResponse('/api/status', {
      hostname: 'test.com',
      jobs: [
        createMockJob({ job_id: 'multi-callback', state: 'PD', hostname: 'test.com' }),
      ],
      timestamp: new Date().toISOString(),
      query_time: '0.123s',
      array_groups: [],
    });

    // Spy on syncAllHosts
    const syncSpy = vi.spyOn(manager, 'syncAllHosts');

    // Start polling
    manager.connectWebSocket();
    await waitForWebSocket(testSetup.mocks.wsFactory);
    simulateWebSocketClose(testSetup.mocks.wsFactory);
    await vi.advanceTimersByTimeAsync(1000);

    syncSpy.mockClear();

    // Advance time for 3 polling intervals
    await vi.advanceTimersByTimeAsync(60000); // First
    await vi.advanceTimersByTimeAsync(60000); // Second
    await vi.advanceTimersByTimeAsync(60000); // Third

    // Should have been called 3 times
    expect(syncSpy).toHaveBeenCalledTimes(3);

    syncSpy.mockRestore();
  });

  it('should verify state actually updates from polling callback', async () => {
    // Initial state: PENDING
    testSetup.mocks.api.setResponse('/api/status', {
      hostname: 'test.com',
      jobs: [
        createMockJob({ job_id: 'state-update-test', state: 'PD', hostname: 'test.com' }),
      ],
      timestamp: new Date().toISOString(),
      query_time: '0.123s',
      array_groups: [],
    });

    // Start polling
    manager.connectWebSocket();
    await waitForWebSocket(testSetup.mocks.wsFactory);
    simulateWebSocketClose(testSetup.mocks.wsFactory);
    await vi.advanceTimersByTimeAsync(1000);

    // Do initial sync to get the job
    await manager.syncAllHosts();
    await vi.advanceTimersByTimeAsync(500);

    // Verify initial state
    let allJobs = get(manager.getAllJobs());
    expect(allJobs.find(j => j.job_id === 'state-update-test')?.state).toBe('PD');

    // Change API response: Job now RUNNING
    testSetup.mocks.api.setResponse('/api/status', {
      hostname: 'test.com',
      jobs: [
        createMockJob({ job_id: 'state-update-test', state: 'R', hostname: 'test.com' }),
      ],
      timestamp: new Date().toISOString(),
      query_time: '0.123s',
      array_groups: [],
    });

    // ⚠️ CRITICAL: Wait for cache to expire (> 60 seconds from lastSync)
    // The cache check in syncHost blocks updates if lastSync is < 60s ago
    await vi.advanceTimersByTimeAsync(61000); // Polling interval + cache expiry

    // Give time for async operations and batch processing
    await vi.advanceTimersByTimeAsync(1000);

    // Check if state was updated
    allJobs = get(manager.getAllJobs());
    const job = allJobs.find(j => j.job_id === 'state-update-test');

    console.log('[TEST] Job after polling with cache expiry:', job);

    // This is the REAL test - did polling fetch and update the state?
    expect(job?.state).toBe('R');
  });

  it('should verify pollingActive state is set correctly', async () => {
    // Connect and close WebSocket
    manager.connectWebSocket();
    await waitForWebSocket(testSetup.mocks.wsFactory);

    // Before close - polling should be inactive
    let state = get(manager.getState());
    expect(state.pollingActive).toBe(false);

    simulateWebSocketClose(testSetup.mocks.wsFactory);
    await vi.advanceTimersByTimeAsync(1000);

    // After close - polling should be active
    state = get(manager.getState());
    expect(state.pollingActive).toBe(true);
  });
});
