import { beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';

beforeEach(() => vi.resetModules());

describe('Appearance preference', () => {
  it('follows OS appearance in system mode and keeps an explicit override', async () => {
    let onChange: (event: { matches: boolean }) => void = () => {};
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false, addEventListener: (_type: string, callback: typeof onChange) => onChange = callback, removeEventListener: vi.fn() })));
    const { theme, resolvedTheme } = await import('./theme');
    theme.set('system');
    expect(get(resolvedTheme)).toBe('light');
    onChange({ matches: true });
    expect(get(resolvedTheme)).toBe('dark');
    expect(document.documentElement).toHaveClass('dark');
    theme.set('light');
    onChange({ matches: true });
    expect(get(resolvedTheme)).toBe('light');
    expect(document.documentElement).not.toHaveClass('dark');
    const toggle = theme.toggle;
    toggle();
    expect(get(resolvedTheme)).toBe('dark');
    expect(localStorage.setItem).toHaveBeenCalledWith('theme', 'dark');
    vi.unstubAllGlobals();
  });
});
