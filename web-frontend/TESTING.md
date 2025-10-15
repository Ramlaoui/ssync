# Frontend Testing Guide

Comprehensive testing setup for the ssync web frontend, covering unit tests, integration tests, and best practices.

## Table of Contents

- [Overview](#overview)
- [Running Tests](#running-tests)
- [Test Structure](#test-structure)
- [Testing Utilities](#testing-utilities)
- [Writing Tests](#writing-tests)
- [Best Practices](#best-practices)
- [Coverage](#coverage)
- [CI/CD Integration](#cicd-integration)

## Overview

The frontend uses **Vitest** as the test runner with the following stack:

- **Vitest**: Fast, Vite-native test runner
- **@testing-library/svelte**: Component testing utilities
- **Happy-DOM**: Lightweight DOM implementation
- **MSW (Mock Service Worker)**: API mocking
- **Custom mocks**: WebSocket and utility mocks

## Running Tests

```bash
# Run tests in watch mode (development)
npm test

# Run tests once (CI)
npm run test:run

# Run tests with UI
npm run test:ui

# Run tests with coverage
npm run test:coverage
```

## Test Structure

Tests are organized by functionality:

```
web-frontend/
├── src/
│   ├── lib/
│   │   ├── JobStateManager.ts
│   │   ├── JobStateManager.test.ts           # Core functionality
│   │   ├── JobStateManager.websocket.test.ts # WebSocket tests
│   │   ├── JobStateManager.refresh.test.ts   # Refresh timing
│   │   └── JobStateManager.edge-cases.test.ts # Edge cases
│   ├── components/
│   │   ├── JobList.svelte
│   │   └── JobList.test.ts                   # Component tests
│   └── test/
│       ├── setup.ts                           # Global test setup
│       └── utils/
│           ├── mockData.ts                    # Test fixtures
│           ├── mockApi.ts                     # API mocking
│           └── mockWebSocket.ts               # WebSocket mocking
└── vitest.config.ts                           # Vitest configuration
```

## Testing Utilities

### Mock Data (`test/utils/mockData.ts`)

Provides reusable test fixtures:

```typescript
import { mockJobs, createMockJob, createMockJobs } from '../test/utils/mockData';

// Use predefined mock jobs
const jobs = mockJobs;

// Create a custom job
const job = createMockJob({
  job_id: '123',
  state: 'R',
  hostname: 'test.com',
});

// Create multiple jobs
const jobs = createMockJobs(10, { hostname: 'test.com' });
```

### API Mocking (`test/utils/mockApi.ts`)

Uses MSW for API request mocking:

```typescript
import { setupMSW, addHandler, createErrorHandler } from '../test/utils/mockApi';

// Setup in test file
setupMSW();

// Add custom handler
addHandler(
  http.get('http://localhost:8042/api/custom', () => {
    return HttpResponse.json({ data: 'test' });
  })
);

// Add error handler
addHandler(createErrorHandler('/api/endpoint', 500, 'Error message'));
```

### WebSocket Mocking (`test/utils/mockWebSocket.ts`)

Provides WebSocket simulation:

```typescript
import { setupWebSocketMock, waitForWebSocket } from '../test/utils/mockWebSocket';

const wsMock = setupWebSocketMock();

// Wait for WebSocket creation
const ws = await waitForWebSocket(wsMock.getAllInstances);

// Simulate events
ws.simulateOpen();
ws.simulateMessage({ type: 'job_update', job_id: '123', ... });
ws.simulateError();
ws.simulateClose();
```

## Writing Tests

### Basic Test Structure

```typescript
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { setupMSW } from '../test/utils/mockApi';

setupMSW(); // Setup API mocking

describe('Feature Name', () => {
  beforeEach(() => {
    vi.useFakeTimers(); // For time-based tests
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllTimers();
  });

  it('should do something', () => {
    // Arrange
    const input = 'test';

    // Act
    const result = someFunction(input);

    // Assert
    expect(result).toBe('expected');
  });
});
```

### Testing JobStateManager

```typescript
import { JobStateManager } from './JobStateManager';
import { get } from 'svelte/store';

describe('JobStateManager', () => {
  let manager: JobStateManager;

  beforeEach(async () => {
    manager = new (JobStateManager as any)();
    await manager.initialize();
  });

  afterEach(() => {
    manager.destroy();
  });

  it('should manage job state', () => {
    const allJobs = get(manager.getAllJobs());
    expect(allJobs).toEqual([]);
  });
});
```

### Testing Components

```typescript
import { render, screen, fireEvent } from '@testing-library/svelte';
import JobList from './JobList.svelte';

describe('JobList Component', () => {
  it('should render jobs', () => {
    render(JobList, {
      props: {
        hostname: 'test.com',
        jobs: [createMockJob()],
        queryTime: '0.1s',
        loading: false,
      },
    });

    expect(screen.getByText('test.com')).toBeInTheDocument();
  });

  it('should handle clicks', async () => {
    const { component } = render(JobList, { props: { ... } });

    let clicked = false;
    component.$on('jobSelect', () => { clicked = true; });

    await fireEvent.click(screen.getByRole('button'));
    expect(clicked).toBe(true);
  });
});
```

### Testing Async Behavior

```typescript
it('should handle async operations', async () => {
  const promise = manager.syncAllHosts();

  // Advance timers for async operations
  await vi.advanceTimersByTimeAsync(1000);

  await promise;

  const state = get(manager.getState());
  expect(state.jobCache.size).toBeGreaterThan(0);
});
```

### Testing WebSocket Messages

```typescript
it('should process WebSocket messages', async () => {
  const ws = wsMock.getLastInstance();

  ws?.simulateMessage({
    type: 'job_update',
    job_id: '123',
    hostname: 'test.com',
    job: createMockJob({ job_id: '123' }),
  });

  await vi.advanceTimersByTimeAsync(200);

  const job = get(manager.getJob('123', 'test.com'));
  expect(job).toBeDefined();
});
```

## Best Practices

### 1. Use Descriptive Test Names

```typescript
// Good
it('should cache running jobs for 60 seconds')

// Bad
it('test cache')
```

### 2. Follow AAA Pattern

```typescript
it('should update job state', () => {
  // Arrange
  const job = createMockJob({ state: 'PD' });

  // Act
  manager.updateJob(job.id, { state: 'R' });

  // Assert
  const updated = manager.getJob(job.id);
  expect(updated.state).toBe('R');
});
```

### 3. Test One Thing Per Test

```typescript
// Good - tests single behavior
it('should add job to cache')
it('should update existing job')
it('should deduplicate jobs')

// Bad - tests multiple behaviors
it('should manage jobs')
```

### 4. Use Fake Timers for Time-based Tests

```typescript
beforeEach(() => {
  vi.useFakeTimers();
});

it('should expire cache after timeout', () => {
  manager.addJob(job);

  vi.advanceTimersByTime(61000); // 61 seconds

  expect(manager.isJobCacheValid(jobId)).toBe(false);
});
```

### 5. Clean Up After Tests

```typescript
afterEach(() => {
  if (manager) manager.destroy();
  vi.clearAllTimers();
  vi.clearAllMocks();
});
```

### 6. Mock External Dependencies

```typescript
// Mock localStorage
global.localStorage = {
  getItem: vi.fn(),
  setItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn(),
} as any;
```

### 7. Test Edge Cases

```typescript
describe('Edge Cases', () => {
  it('should handle empty job list')
  it('should handle malformed data')
  it('should handle network errors')
  it('should handle concurrent updates')
  it('should handle very large datasets')
});
```

### 8. Use Meaningful Assertions

```typescript
// Good
expect(jobs).toHaveLength(5);
expect(job.state).toBe('R');
expect(hostState.status).toBe('connected');

// Avoid
expect(true).toBeTruthy();
expect(jobs.length > 0).toBe(true);
```

## Test Coverage Areas

### JobStateManager Tests

#### Core Functionality (`JobStateManager.test.ts`)
- ✅ Initialization
- ✅ Job cache management (add, update, retrieve)
- ✅ Cache validation by job state
- ✅ Update batching and deduplication
- ✅ Host state tracking
- ✅ Derived stores (filtering, querying)
- ✅ Performance metrics

#### WebSocket Handling (`JobStateManager.websocket.test.ts`)
- ✅ Connection lifecycle (connect, open, close, reconnect)
- ✅ Message handling (initial, job_update, state_change, batch_update)
- ✅ Priority updates for current view
- ✅ Fallback to polling
- ✅ Health monitoring
- ✅ Error handling

#### Refresh Timing (`JobStateManager.refresh.test.ts`)
- ✅ Initial sync behavior
- ✅ Polling intervals (active, background, paused)
- ✅ Cache-based optimization
- ✅ Force refresh
- ✅ State-based cache lifetimes (PD: 30s, R: 60s, CD: 5min)
- ✅ Single job fetching
- ✅ API call optimization
- ✅ Timeout handling

#### Edge Cases (`JobStateManager.edge-cases.test.ts`)
- ✅ Empty states
- ✅ Duplicate jobs
- ✅ Invalid data
- ✅ Large datasets (1000+ jobs)
- ✅ Race conditions
- ✅ Network errors (500, 404, timeout)
- ✅ Memory management
- ✅ Cleanup and destruction

### Component Tests

#### JobList Component (`JobList.test.ts`)
- ✅ Rendering (desktop and mobile layouts)
- ✅ User interactions (clicks, keyboard)
- ✅ Responsive behavior
- ✅ Loading states
- ✅ Data display
- ✅ Multiple jobs
- ✅ Accessibility

## Coverage

View coverage reports:

```bash
npm run test:coverage
```

Coverage is reported in:
- Terminal (text format)
- `coverage/index.html` (HTML format)
- `coverage/coverage-final.json` (JSON format)

Target coverage goals:
- **Statements**: > 80%
- **Branches**: > 75%
- **Functions**: > 80%
- **Lines**: > 80%

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Setup Node
        uses: actions/setup-node@v3
        with:
          node-version: '18'

      - name: Install dependencies
        run: npm ci
        working-directory: ./web-frontend

      - name: Run tests
        run: npm run test:run
        working-directory: ./web-frontend

      - name: Generate coverage
        run: npm run test:coverage
        working-directory: ./web-frontend

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: ./web-frontend/coverage/coverage-final.json
```

## Debugging Tests

### Using Vitest UI

```bash
npm run test:ui
```

Opens an interactive UI at http://localhost:51204

### Debug in VS Code

Add to `.vscode/launch.json`:

```json
{
  "type": "node",
  "request": "launch",
  "name": "Debug Tests",
  "runtimeExecutable": "npm",
  "runtimeArgs": ["run", "test:run"],
  "console": "integratedTerminal",
  "internalConsoleOptions": "neverOpen"
}
```

### Console Output

Tests suppress console.log by default. To see logs:

```typescript
// In test/setup.ts, comment out:
// global.console = { ...console, log: vi.fn(), ... };
```

### Filtering Tests

```bash
# Run specific test file
npm test JobStateManager.test

# Run tests matching pattern
npm test -- --grep "WebSocket"

# Run only this test
it.only('should test specific behavior', () => {
  // ...
});

# Skip this test
it.skip('should test something later', () => {
  // ...
});
```

## Common Issues

### Issue: Tests timeout

**Solution**: Increase timeout in `vitest.config.ts`:

```typescript
export default defineConfig({
  test: {
    testTimeout: 10000,
  },
});
```

### Issue: WebSocket not mocking

**Solution**: Ensure `setupWebSocketMock()` is called before creating manager:

```typescript
beforeEach(() => {
  wsMock = setupWebSocketMock(); // Must be before manager creation
  manager = new JobStateManager();
});
```

### Issue: Timers not advancing

**Solution**: Use `advanceTimersByTimeAsync` for async operations:

```typescript
// For sync code
vi.advanceTimersByTime(1000);

// For async code
await vi.advanceTimersByTimeAsync(1000);
```

### Issue: API calls not mocked

**Solution**: Ensure MSW is set up correctly:

```typescript
import { setupMSW } from '../test/utils/mockApi';

setupMSW(); // Add this at the top level
```

## Additional Resources

- [Vitest Documentation](https://vitest.dev/)
- [Testing Library Documentation](https://testing-library.com/docs/svelte-testing-library/intro)
- [MSW Documentation](https://mswjs.io/)
- [Svelte Testing Best Practices](https://svelte.dev/docs/testing)

## Contributing

When adding new features:

1. Write tests first (TDD approach recommended)
2. Ensure tests cover:
   - Happy path
   - Error cases
   - Edge cases
   - Integration points
3. Run full test suite before committing
4. Update this documentation if adding new testing utilities

## Summary

This testing infrastructure provides:

✅ Comprehensive coverage of job state management
✅ WebSocket and API mocking
✅ Refresh timing verification
✅ Edge case and error handling
✅ Component integration testing
✅ Performance and memory testing
✅ Easy-to-use testing utilities
✅ Fast feedback loop with Vitest

The test suite ensures the job handling feature works correctly, calls the backend at the right times, updates job status properly, and handles all edge cases gracefully.
