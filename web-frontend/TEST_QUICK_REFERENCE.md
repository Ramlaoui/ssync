# Testing Quick Reference

Quick reference for common testing scenarios in the ssync web frontend.

## Running Tests

```bash
npm test                    # Watch mode
npm run test:run            # Single run
npm run test:ui             # Interactive UI
npm run test:coverage       # With coverage
npm test JobStateManager    # Specific file
```

## Common Test Patterns

### Test a Function/Method

```typescript
it('should do something', () => {
  const result = myFunction(input);
  expect(result).toBe(expected);
});
```

### Test Async Behavior

```typescript
it('should handle async operation', async () => {
  await manager.someAsyncMethod();
  expect(get(manager.getState()).value).toBe(expected);
});
```

### Test with Timers

```typescript
beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

it('should timeout after delay', () => {
  manager.startTimer();
  vi.advanceTimersByTime(5000);
  expect(manager.hasTimedOut()).toBe(true);
});
```

### Test WebSocket

```typescript
const wsMock = setupWebSocketMock();
const ws = await waitForWebSocket(wsMock.getAllInstances);

ws.simulateOpen();
ws.simulateMessage({ type: 'update', data: {} });
ws.simulateClose();
```

### Test API Calls

```typescript
setupMSW();

// Custom endpoint
addHandler(
  http.get('http://localhost:8042/api/test', () => {
    return HttpResponse.json({ data: 'test' });
  })
);

// Error response
addHandler(createErrorHandler('/api/test', 500, 'Error'));
```

### Test Components

```typescript
const { component } = render(MyComponent, {
  props: { value: 'test' }
});

// Find elements
screen.getByText('text');
screen.getByRole('button');
screen.getByLabelText('label');

// Interact
await fireEvent.click(element);
await fireEvent.keyDown(element, { key: 'Enter' });

// Listen to events
component.$on('event', (e) => { /* handle */ });
```

### Test Stores

```typescript
import { get } from 'svelte/store';

const value = get(myStore);
expect(value).toBe(expected);

// Subscribe to changes
const unsubscribe = myStore.subscribe(value => {
  console.log('Changed:', value);
});
```

## Mock Data

```typescript
import {
  mockJobs,           // Predefined jobs
  mockHosts,          // Predefined hosts
  createMockJob,      // Create single job
  createMockJobs,     // Create multiple jobs
} from '../test/utils/mockData';

const job = createMockJob({
  job_id: '123',
  state: 'R',
  hostname: 'test.com'
});
```

## Assertions

```typescript
// Equality
expect(value).toBe(5);
expect(obj).toEqual({ key: 'value' });

// Truthiness
expect(value).toBeTruthy();
expect(value).toBeFalsy();
expect(value).toBeNull();
expect(value).toBeUndefined();
expect(value).toBeDefined();

// Numbers
expect(num).toBeGreaterThan(5);
expect(num).toBeLessThan(10);
expect(num).toBeCloseTo(5.5, 1);

// Arrays/Objects
expect(array).toHaveLength(3);
expect(array).toContain(item);
expect(obj).toHaveProperty('key');

// Strings
expect(str).toMatch(/pattern/);
expect(str).toContain('substring');

// DOM (with @testing-library/jest-dom)
expect(element).toBeInTheDocument();
expect(element).toBeVisible();
expect(element).toBeDisabled();
expect(element).toHaveAttribute('href', '/path');
expect(element).toHaveClass('active');
```

## Debugging

```bash
# Run with UI for interactive debugging
npm run test:ui

# Run specific test
npm test -- -t "test name pattern"

# Run only one test
it.only('should test this', () => {});

# Skip a test
it.skip('should test later', () => {});

# View console output
# Comment out console mock in test/setup.ts
```

## Coverage Goals

- Statements: > 80%
- Branches: > 75%
- Functions: > 80%
- Lines: > 80%

## Test File Locations

```
src/lib/JobStateManager.test.ts           # Core tests
src/lib/JobStateManager.websocket.test.ts # WebSocket tests
src/lib/JobStateManager.refresh.test.ts   # Refresh/timing tests
src/lib/JobStateManager.edge-cases.test.ts # Edge cases
src/components/JobList.test.ts            # Component tests
```

## Key Test Scenarios Covered

### JobStateManager
- ✅ Initialization and cleanup
- ✅ Job caching (add, update, deduplicate)
- ✅ Cache validation by state (PD: 30s, R: 60s, CD: 5min)
- ✅ WebSocket connection and reconnection
- ✅ Message handling (all types)
- ✅ Polling fallback (active: 60s, background: 300s)
- ✅ Force refresh bypassing cache
- ✅ Update batching and deduplication
- ✅ Host state tracking and errors
- ✅ Performance metrics
- ✅ Edge cases (empty, invalid data, large datasets)
- ✅ Race conditions (concurrent updates)
- ✅ Network errors (500, 404, timeout)
- ✅ Memory management

### Components
- ✅ Rendering (desktop/mobile)
- ✅ User interactions
- ✅ Event emissions
- ✅ Loading states
- ✅ Responsive behavior
- ✅ Accessibility

## Common Mistakes to Avoid

❌ Not using fake timers for time-based tests
❌ Not cleaning up (destroy, clear timers/mocks)
❌ Testing implementation details instead of behavior
❌ Not handling async properly (missing await)
❌ Not mocking external dependencies
❌ Writing tests that depend on each other
❌ Testing too many things in one test

## Getting Help

- See full documentation: `TESTING.md`
- Vitest docs: https://vitest.dev/
- Testing Library: https://testing-library.com/
- MSW: https://mswjs.io/
