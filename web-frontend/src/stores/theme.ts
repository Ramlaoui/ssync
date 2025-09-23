import { writable, derived } from 'svelte/store';

type Theme = 'light' | 'dark' | 'system';

// Check if we're in browser
const browser = typeof window !== 'undefined';

// Create the store with system preference as default
function createThemeStore() {
    // Get initial theme from localStorage or default to system
    const storedTheme = browser ? localStorage.getItem('theme') as Theme : 'system';
    const initialTheme: Theme = storedTheme || 'system';

    const { subscribe, set, update } = writable<Theme>(initialTheme);

    return {
        subscribe,
        set: (theme: Theme) => {
            if (browser) {
                localStorage.setItem('theme', theme);
                applyTheme(theme);
            }
            set(theme);
        },
        toggle: () => {
            update(current => {
                const next = current === 'dark' ? 'light' : 'dark';
                if (browser) {
                    localStorage.setItem('theme', next);
                    applyTheme(next);
                }
                return next;
            });
        },
        init: () => {
            if (browser) {
                const stored = localStorage.getItem('theme') as Theme;
                const theme = stored || 'system';
                applyTheme(theme);
                set(theme);
            }
        }
    };
}

// Apply theme to document
function applyTheme(theme: Theme) {
    if (!browser) return;

    const root = document.documentElement;

    if (theme === 'system') {
        // Check system preference
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        if (prefersDark) {
            root.classList.add('dark');
        } else {
            root.classList.remove('dark');
        }
    } else if (theme === 'dark') {
        root.classList.add('dark');
    } else {
        root.classList.remove('dark');
    }
}

// Create the store
export const theme = createThemeStore();

// Derived store for actual theme (resolving 'system' to light/dark)
export const resolvedTheme = derived(theme, ($theme) => {
    if (!browser) return 'light';

    if ($theme === 'system') {
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    return $theme;
});

// Listen for system theme changes when in system mode
if (browser) {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    mediaQuery.addEventListener('change', (e) => {
        const currentTheme = localStorage.getItem('theme') as Theme;
        if (currentTheme === 'system' || !currentTheme) {
            applyTheme('system');
        }
    });
}

// Initialize theme on module load
if (browser) {
    theme.init();
}