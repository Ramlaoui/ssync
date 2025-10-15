# Testing Quick Reference Guide

## Running Tests

```bash
# Run all tests
npm run test:run

# Run specific test file
npm run test:run -- src/components/JobList.test.ts

# Run tests in watch mode
npm run test

# Run with coverage
npm run test:coverage
```

## Current Test Status

✅ **104 passing** | ❌ **18 failing** | ⏭️ **1 skipped**

- **Component Tests:** 18/18 passing (100%) ✅
- **Integration Tests:** 86/104 passing (86%)

## Writing New Tests

### Component Tests (Svelte 5)

```typescript
import { mount, unmount, flushSync } from 'svelte';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import MyComponent from './MyComponent.svelte';

describe('MyComponent', () => {
  let container: HTMLElement;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
  });

  afterEach(() => {
    if (container && container.parentNode) {
      container.parentNode.removeChild(container);
    }
  });

  it('should render', () => {
    mount(MyComponent, {
      target: container,
      props: { title: 'Test' }
    });

    expect(container.textContent).toContain('Test');
  });
});
```

### JobStateManager Tests (with DI)

```typescript
import { createTestJobStateManager } from '../test/utils/testFactory';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

describe('MyFeature', () => {
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

  it('should do something', async () => {
    // Configure mock API response
    testSetup.mocks.api.setResponse('/api/status', {
      hostname: 'test.com',
      jobs: mockJobs,
      timestamp: new Date().toISOString(),
    });

    // Test your feature
    await manager.syncHost('test.com');

    // Assert
    expect(testSetup.mocks.api.getCallCount()).toBeGreaterThan(0);
  });
});
```

## Common Patterns

### Testing API Calls

```typescript
// Clear previous calls
testSetup.mocks.api.clearCalls();

// Do something that makes API calls
await manager.syncHost('test.com');

// Assert calls were made
expect(testSetup.mocks.api.getCallCount()).toBeGreaterThan(0);

// Check specific parameters
const calls = vi.mocked(testSetup.mocks.api.get).mock.calls;
expect(calls[0][0]).toContain('force_refresh=true');
```

### Testing WebSocket

```typescript
// Simulate WebSocket opening
const ws = testSetup.mocks.wsFactory.getLastInstance();
simulateWebSocketOpen(testSetup.mocks.wsFactory);

// Send message
ws?.simulateMessage({
  type: 'update',
  job: mockJob,
});

// Simulate error/close
simulateWebSocketError(testSetup.mocks.wsFactory);
simulateWebSocketClose(testSetup.mocks.wsFactory);
```

### Testing with Fake Timers

```typescript
beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllTimers();
});

it('should poll after 60s', async () => {
  await vi.advanceTimersByTimeAsync(60000);
  expect(pollingHappened).toBe(true);
});
```

### Custom Mock Responses

```typescript
// Return specific data for a test
testSetup.mocks.api.setResponse('/api/status?host=test.com', {
  hostname: 'test.com',
  jobs: [specificJob],
  timestamp: new Date().toISOString(),
});

// Return empty for empty state tests
testSetup.mocks.api.setResponse('/api/status', {
  hostname: 'test.com',
  jobs: [], // Empty!
  timestamp: new Date().toISOString(),
});
```

## Troubleshooting

### "mount(...) is not available on the server"

✅ **Fixed** - Custom Vite plugin in `vitest.config.ts` resolves this

If you see this error again, make sure:
1. You're using `jsdom` environment (not happy-dom)
2. The custom resolver plugin is active
3. You're importing from 'svelte' not 'svelte/server'

### "Cannot assign to read only property 'WebSocket'"

✅ **Fixed** - Using `Object.defineProperty` in mockWebSocket.ts

If you see this, check that `setupWebSocketMock()` is using the correct pattern.

### Tests timing out

Increase timeouts in `vitest.config.ts`:
```typescript
test: {
  testTimeout: 15000,  // 15 seconds
  hookTimeout: 15000,
}
```

Or for specific tests:
```typescript
it('slow test', async () => {
  // ...
}, { timeout: 30000 });
```

### Mock API not working

Make sure you're using the DI pattern:
```typescript
// ✅ Good
const testSetup = createTestJobStateManager();
testSetup.mocks.api.setResponse('/api/status', data);

// ❌ Bad - using MSW instead
addHandler(http.get('/api/status', () => HttpResponse.json(data)));
```

## Best Practices

1. **Always use `createTestJobStateManager()`** - Provides isolated test environment
2. **Clean up after each test** - Call `manager.destroy()` in `afterEach`
3. **Use fake timers** - Avoid real delays, use `vi.advanceTimersByTimeAsync()`
4. **Configure mock responses** - Don't rely on defaults if test needs specific data
5. **Clear API call counts** - Use `clearCalls()` before testing specific behavior
6. **Test one thing** - Keep tests focused and simple
7. **Use descriptive names** - "should do X when Y" format

## Common Imports

```typescript
// Testing framework
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// Svelte
import { mount, unmount, flushSync } from 'svelte';
import { get } from 'svelte/store';

// Test utilities
import { createTestJobStateManager, simulateWebSocketOpen } from '../test/utils/testFactory';
import { mockJobs, createMockJob } from '../test/utils/mockData';

// Component/code to test
import MyComponent from './MyComponent.svelte';
import { MyClass } from './MyClass';
```

## File Structure

```
src/
├── test/
│   ├── setup.ts              # Global test setup
│   └── utils/
│       ├── testFactory.ts    # DI test factory
│       ├── mockWebSocket.ts  # WebSocket mocks
│       ├── mockApi.ts        # MSW setup (rarely used now)
│       └── mockData.ts       # Shared test data
├── components/
│   ├── MyComponent.svelte
│   └── MyComponent.test.ts   # Component tests
└── lib/
    ├── MyClass.ts
    └── MyClass.test.ts        # Unit tests
```

## Resources

- [Vitest Docs](https://vitest.dev/)
- [Svelte 5 Testing Guide](https://svelte.dev/docs/svelte/testing)
- [TEST_FIXES_SUMMARY.md](./TEST_FIXES_SUMMARY.md) - Detailed technical breakdown

---

**Questions?** Check TEST_FIXES_SUMMARY.md or ask in the team chat.
