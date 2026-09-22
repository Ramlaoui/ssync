import { derived, get, writable } from 'svelte/store';
import { safeGetItem, safeSetItem } from '../lib/safeStorage';
type Theme = 'light' | 'dark' | 'system';
const browser = typeof window !== 'undefined';
const media = browser ? window.matchMedia('(prefers-color-scheme: dark)') : null;
const systemDark = writable(media?.matches ?? false);
const validTheme = (value: string | null): Theme => value === 'light' || value === 'dark' ? value : 'system';
const preference = writable<Theme>(validTheme(safeGetItem('theme')));
export const resolvedTheme = derived([preference, systemDark], ([$theme, $dark]) => $theme === 'system' ? ($dark ? 'dark' : 'light') : $theme);
export const theme = {
    subscribe: preference.subscribe,
    set(value: Theme) { safeSetItem('theme', value); preference.set(value); },
    toggle() { theme.set(get(resolvedTheme) === 'dark' ? 'light' : 'dark'); },
    init() { systemDark.set(media?.matches ?? false); preference.set(validTheme(safeGetItem('theme'))); },
};
const unsubscribe = resolvedTheme.subscribe(value => {
    if (!browser)
        return;
    document.documentElement.classList.toggle('dark', value === 'dark');
    document.documentElement.dataset.theme = value;
});
const onSystemChange = (event: MediaQueryListEvent) => systemDark.set(event.matches);
media?.addEventListener('change', onSystemChange);
if (import.meta.hot)
    import.meta.hot.dispose(() => { unsubscribe(); media?.removeEventListener('change', onSystemChange); });
