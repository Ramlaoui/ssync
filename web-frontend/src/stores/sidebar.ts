import { writable } from 'svelte/store';

// Global store for sidebar visibility
export const sidebarOpen = writable<boolean>(true);
