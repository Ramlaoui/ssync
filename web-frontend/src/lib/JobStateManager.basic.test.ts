/**
 * Basic JobStateManager tests
 * Simplified tests that work with the current architecture using DI
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { get } from 'svelte/store';
import { createTestJobStateManager } from '../test/utils/testFactory';
import { setupMSW } from '../test/utils/mockApi';
import { createMockJob } from '../test/utils/mockData';
import type { JobStateManager } from './JobStateManager';

setupMSW();

describe('JobStateManager - Basic Tests', () => {
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

  it('should create a manager instance', () => {
    expect(manager).toBeDefined();
    expect(manager.getState).toBeDefined();
    expect(manager.getAllJobs).toBeDefined();
  });

  it('should have empty initial state', () => {
    const state = get(manager.getState());
    expect(state.jobCache.size).toBe(0);
  });

  it('should return empty jobs array initially', () => {
    const jobs = get(manager.getAllJobs());
    expect(jobs).toEqual([]);
  });

  it('should provide connection status store', () => {
    const status = get(manager.getConnectionStatus());
    expect(status).toHaveProperty('source');
    expect(status).toHaveProperty('connected');
    expect(status).toHaveProperty('healthy');
  });
});
