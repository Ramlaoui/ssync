import { afterEach, describe, expect, it, vi } from 'vitest';
import { focusTrap } from './focusTrap';

afterEach(() => {
  vi.useRealTimers();
  document.body.innerHTML = '';
});

describe('focusTrap', () => {
  it('focuses an explicitly selected target after the trap is mounted', () => {
    vi.useFakeTimers();
    const node = document.createElement('div');
    const target = document.createElement('input');
    target.id = 'dialog-search';
    node.append(target);
    document.body.append(node);

    const action = focusTrap(node, { initialFocus: '#dialog-search' });

    expect(document.activeElement).not.toBe(target);
    vi.runOnlyPendingTimers();
    expect(document.activeElement).toBe(target);

    action.destroy();
    vi.runOnlyPendingTimers();
  });

  it('cancels pending initial focus when the trap is destroyed', () => {
    vi.useFakeTimers();
    const restore = document.createElement('button');
    const node = document.createElement('div');
    const target = document.createElement('input');
    target.id = 'dialog-search';
    node.append(target);
    document.body.append(restore, node);
    restore.focus();

    const action = focusTrap(node, { initialFocus: '#dialog-search', restoreFocus: restore });
    action.destroy();
    vi.runOnlyPendingTimers();

    expect(document.activeElement).toBe(restore);
    expect(document.activeElement).not.toBe(target);
  });
});
