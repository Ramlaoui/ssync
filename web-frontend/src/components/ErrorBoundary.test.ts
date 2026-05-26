import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushSync, mount, tick, unmount } from 'svelte';
import ErrorBoundary from './ErrorBoundary.svelte';

describe('ErrorBoundary', () => {
  let container: HTMLElement;
  let component: Record<string, unknown> | undefined;

  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    container = document.createElement('div');
    document.body.appendChild(container);
  });

  afterEach(() => {
    if (component) {
      unmount(component as never);
      component = undefined;
    }
    container.remove();
    vi.restoreAllMocks();
  });

  it('ignores opaque script errors without crashing the app', async () => {
    component = mount(ErrorBoundary, {
      target: container,
    });
    await tick();

    const handleError = window.onerror as
      | ((
          message: string,
          source: string,
          line: number,
          column: number,
          error: Error | null,
        ) => boolean | void)
      | null;
    const handled = handleError?.('Script error.', '', 0, 0, null);
    flushSync();

    expect(handled).toBe(true);
    expect(container.querySelector('.error-boundary')).toBeFalsy();
  });

  it('still renders the boundary for actionable script errors', async () => {
    component = mount(ErrorBoundary, {
      target: container,
    });
    await tick();

    const error = new Error('boom');
    const handled = window.onerror?.('boom', 'app.js', 10, 2, error);
    flushSync();

    expect(handled).toBe(true);
    expect(container.querySelector('.error-boundary')).toBeTruthy();
    expect(container.textContent).toContain('boom');
  });
});
