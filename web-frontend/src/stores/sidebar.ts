import { writable } from 'svelte/store';

// Global store for sidebar visibility
const defaultSidebarOpen =
  typeof window === 'undefined' ? true : window.innerWidth >= 768;

export const sidebarOpen = writable<boolean>(defaultSidebarOpen);
